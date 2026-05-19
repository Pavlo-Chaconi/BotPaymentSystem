import aiohttp
import json
import uuid
import time
from config import XUI_URL, XUI_USERNAME, XUI_PASSWORD, XUI_INBOUND_ID

import logging

logger = logging.getLogger(__name__)

class XuiAPI:
    def __init__(self):
        self.base_url = XUI_URL.rstrip("/")
        self.username = XUI_USERNAME
        self.password = XUI_PASSWORD
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def login(self):
        session = await self._get_session()
        login_data = {
            "username": self.username,
            "password": self.password
        }
        try:
            async with session.post(f"{self.base_url}/login", data=login_data) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("success"):
                        return True
                    else:
                        logger.error(f"3x-ui login failed: {result}")
                else:
                    text = await response.text()
                    logger.error(f"3x-ui login HTTP {response.status}: {text}")
                return False
        except Exception as e:
            logger.error(f"3x-ui login exception: {e}")
            return False

    async def add_client(self, email: str, sub_id: str, expiry_time: int = 0, total_gb: int = 0):
        """
        expiry_time: in milliseconds
        total_gb: in bytes, 0 means unlimited
        """
        session = await self._get_session()
        client_uuid = str(uuid.uuid4())
        
        client_data = {
            "id": client_uuid,
            "alterId": 0,
            "email": email,
            "limitIp": 0,
            "totalGB": total_gb,
            "expiryTime": expiry_time,
            "enable": True,
            "tgId": "",
            "subId": sub_id
        }
        
        payload = {
            "id": XUI_INBOUND_ID,
            "settings": json.dumps({"clients": [client_data]})
        }

        async with session.post(f"{self.base_url}/panel/api/inbounds/addClient", json=payload) as response:
            if response.status == 200:
                res = await response.json()
                if res.get("success"):
                    return client_uuid
            if response.status == 401:
                await self.login()
                async with session.post(f"{self.base_url}/panel/api/inbounds/addClient", json=payload) as retry_resp:
                    if retry_resp.status == 200:
                        retry_res = await retry_resp.json()
                        if retry_res.get("success"):
                            return client_uuid
        return None

    async def update_client_expiry(self, client_uuid: str, new_expiry_time: int):
        # First, we need to fetch existing client data to not overwrite other fields
        clients = await self.get_inbound_clients(XUI_INBOUND_ID)
        target_client = None
        for c in clients:
            if c.get("id") == client_uuid:
                target_client = c
                break
                
        if not target_client:
            logger.error(f"Client {client_uuid} not found for update")
            return False
            
        target_client["expiryTime"] = new_expiry_time
        
        payload = {
            "id": XUI_INBOUND_ID,
            "settings": json.dumps({"clients": [target_client]})
        }
        
        session = await self._get_session()
        async with session.post(f"{self.base_url}/panel/api/inbounds/updateClient/{client_uuid}", json=payload) as response:
            if response.status == 200:
                res = await response.json()
                return res.get("success", False)
            elif response.status == 401:
                await self.login()
                async with session.post(f"{self.base_url}/panel/api/inbounds/updateClient/{client_uuid}", json=payload) as retry_resp:
                    if retry_resp.status == 200:
                        retry_res = await retry_resp.json()
                        return retry_res.get("success", False)
        return False

    async def get_client_traffic(self, email: str):
        session = await self._get_session()
        async with session.get(f"{self.base_url}/panel/api/inbounds/getClientTraffics") as response:
            if response.status == 200:
                res = await response.json()
                if res.get("success") and res.get("obj"):
                    traffics = res["obj"]
                    for t in traffics:
                        if t.get("email") == email:
                            return t
            elif response.status == 401:
                await self.login()
                async with session.get(f"{self.base_url}/panel/api/inbounds/getClientTraffics") as retry_resp:
                    if retry_resp.status == 200:
                        retry_res = await retry_resp.json()
                        if retry_res.get("success") and retry_res.get("obj"):
                            traffics = retry_res["obj"]
                            for t in traffics:
                                if t.get("email") == email:
                                    return t
        return None

    async def get_inbound_clients(self, inbound_id: int):
        session = await self._get_session()
        async with session.get(f"{self.base_url}/panel/api/inbounds/get/{inbound_id}") as response:
            if response.status == 200:
                res = await response.json()
                if res.get("success") and res.get("obj"):
                    obj = res["obj"]
                    settings_str = obj.get("settings", "{}")
                    try:
                        settings = json.loads(settings_str)
                        return settings.get("clients", [])
                    except json.JSONDecodeError:
                        logger.error("Failed to decode settings JSON from 3x-ui")
                        return []
            elif response.status == 401:
                await self.login()
                async with session.get(f"{self.base_url}/panel/api/inbounds/get/{inbound_id}") as retry_resp:
                    if retry_resp.status == 200:
                        retry_res = await retry_resp.json()
                        if retry_res.get("success") and retry_res.get("obj"):
                            obj = retry_res["obj"]
                            settings_str = obj.get("settings", "{}")
                            try:
                                settings = json.loads(settings_str)
                                return settings.get("clients", [])
                            except json.JSONDecodeError:
                                return []
        return []

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

xui_api = XuiAPI()
