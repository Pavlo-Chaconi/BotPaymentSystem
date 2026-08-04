import os
import asyncpg
from config import DATABASE_URL
import logging

logger = logging.getLogger(__name__)

pool: asyncpg.Pool = None

async def init_db():
    global pool
    logger.info("Connecting to PostgreSQL...")
    pool = await asyncpg.create_pool(DATABASE_URL)
    
    async with pool.acquire() as conn:
        # Table for telegram users
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username VARCHAR(255),
                full_name VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table for subscriptions (links user to 3x-ui client)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                client_email VARCHAR(255) UNIQUE NOT NULL,
                client_uuid VARCHAR(255) UNIQUE NOT NULL,
                sub_id VARCHAR(255),
                status VARCHAR(50) DEFAULT 'active', -- active, expired
                expires_at TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id)
            )
        ''')
        
        # In case the table already existed before sub_id was added
        try:
            await conn.execute('ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS sub_id VARCHAR(255)')
        except Exception:
            pass

        # Tracks whether the "expires in ~7 days" reminder was already sent for
        # the subscription's current expiry (reset whenever expires_at changes)
        try:
            await conn.execute('ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS reminder_sent BOOLEAN DEFAULT FALSE')
        except Exception:
            pass
            
        # Table for payments (Platega.io gateway transactions)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                amount INTEGER NOT NULL,
                months INTEGER NOT NULL,
                status VARCHAR(50) DEFAULT 'pending', -- pending, successful, rejected
                platega_transaction_id VARCHAR(255) UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id)
            )
        ''')

        # In case the table already existed before platega_transaction_id was added
        try:
            await conn.execute('ALTER TABLE payments ADD COLUMN IF NOT EXISTS platega_transaction_id VARCHAR(255) UNIQUE')
        except Exception:
            pass
    logger.info("Database initialized.")

async def add_user(telegram_id: int, username: str, full_name: str) -> bool:
    """Upserts the user (keeping username/full_name fresh) and returns True if this was a first-time registration."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow('''
            INSERT INTO users (telegram_id, username, full_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (telegram_id) DO UPDATE
            SET username = EXCLUDED.username, full_name = EXCLUDED.full_name
            RETURNING (xmax = 0) AS is_new
        ''', telegram_id, username, full_name)
        return row["is_new"]

async def add_subscription(user_id: int, client_email: str, client_uuid: str, sub_id: str, expires_at):
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO subscriptions (user_id, client_email, client_uuid, sub_id, expires_at)
            VALUES ($1, $2, $3, $4, $5)
        ''', user_id, client_email, client_uuid, sub_id, expires_at)

async def extend_subscription(user_id: int, new_expires_at):
    # cb_profile also calls this just to sync expires_at from 3x-ui on every view,
    # so only reset the reminder flag when the expiry actually moves — otherwise
    # a user re-opening their profile right after a reminder would clear it and
    # cause the reminder to resend on the next scheduler pass.
    async with pool.acquire() as conn:
        await conn.execute('''
            UPDATE subscriptions
            SET expires_at = $1,
                reminder_sent = CASE WHEN expires_at IS DISTINCT FROM $1 THEN FALSE ELSE reminder_sent END
            WHERE user_id = $2 AND status = 'active'
        ''', new_expires_at, user_id)

async def get_active_subscription(user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow('''
            SELECT * FROM subscriptions 
            WHERE user_id = $1 AND status = 'active'
            ORDER BY id DESC LIMIT 1
        ''', user_id)

async def create_gateway_payment(user_id: int, amount: int, months: int, platega_transaction_id: str):
    async with pool.acquire() as conn:
        return await conn.fetchval('''
            INSERT INTO payments (user_id, amount, months, platega_transaction_id)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        ''', user_id, amount, months, platega_transaction_id)

async def get_payment(payment_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM payments WHERE id = $1', payment_id)

async def get_payment_by_platega_id(platega_transaction_id: str):
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM payments WHERE platega_transaction_id = $1', platega_transaction_id)

async def update_payment_status(payment_id: int, status: str):
    async with pool.acquire() as conn:
        await conn.execute('UPDATE payments SET status = $1 WHERE id = $2', status, payment_id)

async def import_subscription(telegram_id: int, client_email: str, client_uuid: str, sub_id: str, expires_at):
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Create user if not exists (we only have their ID for now)
            await conn.execute('''
                INSERT INTO users (telegram_id, username, full_name)
                VALUES ($1, $2, $3)
                ON CONFLICT (telegram_id) DO NOTHING
            ''', telegram_id, f"user_{telegram_id}", "Imported User")

            # A user has at most one active subscription; importing a different
            # client for them replaces it instead of leaving two rows active
            # (extend_subscription updates by user_id+status='active' and would
            # otherwise touch both).
            replaced = await conn.fetch('''
                UPDATE subscriptions SET status = 'replaced'
                WHERE user_id = $1 AND status = 'active' AND client_uuid != $2
                RETURNING id
            ''', telegram_id, client_uuid)

            # Insert subscription, updating if it exists
            await conn.execute('''
                INSERT INTO subscriptions (user_id, client_email, client_uuid, sub_id, expires_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (client_uuid) DO UPDATE
                SET user_id = EXCLUDED.user_id,
                    client_email = EXCLUDED.client_email,
                    sub_id = EXCLUDED.sub_id,
                    expires_at = EXCLUDED.expires_at,
                    status = 'active',
                    reminder_sent = FALSE
            ''', telegram_id, client_email, client_uuid, sub_id, expires_at)

            return len(replaced) > 0

async def get_subscriptions_expiring_soon(days: int):
    async with pool.acquire() as conn:
        return await conn.fetch('''
            SELECT * FROM subscriptions
            WHERE status = 'active'
              AND reminder_sent = FALSE
              AND expires_at > NOW()
              AND expires_at <= NOW() + ($1 || ' days')::interval
        ''', str(days))

async def mark_reminder_sent(subscription_id: int):
    async with pool.acquire() as conn:
        await conn.execute('UPDATE subscriptions SET reminder_sent = TRUE WHERE id = $1', subscription_id)

async def close_db():
    if pool:
        await pool.close()
