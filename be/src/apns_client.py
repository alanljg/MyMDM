import asyncio
import logging
from aioapns import APNs, NotificationRequest, PushType
import os

logger = logging.getLogger(__name__)

class APNsClient:
    def __init__(self):
        self.client = None
        self.cert_path = os.getenv('APNS_CERT_PATH', './certs/mdm_push_cert.pem')
        self.key_path = os.getenv('APNS_KEY_PATH', './certs/mdm_push_key.pem')
        self.use_sandbox = os.getenv('APNS_USE_SANDBOX', 'true').lower() == 'true'
    
    async def get_client(self):
        if self.client is None:
            self.client = APNs(
                client_cert=self.cert_path,
                use_sandbox=self.use_sandbox,
            )
        return self.client
    
    async def close(self):
        if self.client:
            await self.client.close()

apns_client = APNsClient()

async def send_apns_notification(token: str, push_magic: str, topic: str):
    '''Send APNs notification to device to check for MDM commands'''
    try:
        client = await apns_client.get_client()
        
        # MDM push notification payload
        request = NotificationRequest(
            device_token=token,
            message={
                "mdm": push_magic
            },
            push_type=PushType.MDM,
            topic=topic
        )
        
        response = await client.send_notification(request)
        
        if response.is_successful:
            logger.info(f"APNs notification sent successfully to {token[:10]}...")
            return True
        else:
            logger.error(f"APNs notification failed: {response.description}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending APNs notification: {e}")
        return False

async def send_bulk_notifications(devices: list):
    '''Send APNs notifications to multiple devices'''
    tasks = []
    for device in devices:
        task = send_apns_notification(
            device['token'],
            device['push_magic'],
            device.get('topic', os.getenv('MDM_TOPIC'))
        )
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results