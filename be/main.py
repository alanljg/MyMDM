from src.apns_client import send_apns_notification
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import JSONResponse
import plistlib
import uuid
import uvicorn
from datetime import datetime
from typing import Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Apple MDM Server", version="1.0.0")

# In-memory storage (replace with database in production)
enrolled_devices = {}
pending_commands = {}

# MDM Configuration
MDM_CONFIG = {
    "server_url": "https://your-mdm-server.com",
    "checkin_url": "/mdm/checkin",
    "command_url": "/mdm/command",
    "organization": "Your Organization",
    "topic": "com.apple.mgmt.External.your-uuid"  # APNs topic
}


# ==================== Utility Functions ====================

def parse_plist(data: bytes) -> dict:
    """Parse plist data from request body"""
    try:
        return plistlib.loads(data)
    except Exception as e:
        logger.error(f"Failed to parse plist: {e}")
        raise HTTPException(status_code=400, detail="Invalid plist data")


def create_plist_response(data: dict) -> Response:
    """Create plist response"""
    plist_data = plistlib.dumps(data)
    return Response(content=plist_data, media_type="application/xml")


# ==================== MDM Endpoints ====================

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "service": "Apple MDM Server"}


@app.get("/enroll")
async def enrollment_profile():
    """Generate MDM enrollment profile"""
    from be.src.certificate_utils import sign_profile
    
    profile = {
        "PayloadContent": [{
            "PayloadType": "com.apple.mdm",
            "PayloadVersion": 1,
            "PayloadIdentifier": f"com.yourorg.mdm.{uuid.uuid4()}",
            "PayloadUUID": str(uuid.uuid4()),
            "PayloadDisplayName": "MDM Enrollment",
            "PayloadDescription": "Enrolls device into MDM",
            "PayloadOrganization": MDM_CONFIG["organization"],
            "CheckInURL": f"{MDM_CONFIG['server_url']}{MDM_CONFIG['checkin_url']}",
            "ServerURL": f"{MDM_CONFIG['server_url']}{MDM_CONFIG['command_url']}",
            "Topic": MDM_CONFIG["topic"],
            "IdentityCertificateUUID": str(uuid.uuid4()),
            "ServerCapabilities": ["com.apple.mdm.per-user-connections"],
            "AccessRights": 8191,  # Full access
        }],
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"com.yourorg.profile.{uuid.uuid4()}",
        "PayloadUUID": str(uuid.uuid4()),
        "PayloadDisplayName": "MDM Enrollment Profile",
        "PayloadDescription": "Install this profile to enroll in MDM",
        "PayloadOrganization": MDM_CONFIG["organization"],
    }
    
    # Sign the profile with vendor certificate
    signed_profile = sign_profile(profile)
    
    return Response(
        content=signed_profile,
        media_type="application/x-apple-aspen-config",
        headers={
            "Content-Disposition": "attachment; filename=enrollment.mobileconfig"
        }
    )


@app.put("/mdm/checkin")
async def mdm_checkin(request: Request):
    """Handle MDM check-in messages (Authenticate, TokenUpdate, CheckOut)"""
    body = await request.body()
    data = parse_plist(body)
    
    message_type = data.get("MessageType")
    udid = data.get("UDID")
    
    logger.info(f"CheckIn - MessageType: {message_type}, UDID: {udid}")
    
    if message_type == "Authenticate":
        # Device is authenticating
        logger.info(f"Device {udid} authenticating")
        return Response(status_code=200)
    
    elif message_type == "TokenUpdate":
        # Device is providing push token
        token = data.get("Token")
        push_magic = data.get("PushMagic")
        unlock_token = data.get("UnlockToken")
        
        enrolled_devices[udid] = {
            "udid": udid,
            "token": token.hex() if token else None,
            "push_magic": push_magic,
            "unlock_token": unlock_token.hex() if unlock_token else None,
            "enrolled_at": datetime.utcnow().isoformat(),
            "last_seen": datetime.utcnow().isoformat(),
            "lost_mode_enabled": False
        }
        
        logger.info(f"Device {udid} token updated")
        return Response(status_code=200)
    
    elif message_type == "CheckOut":
        # Device is un-enrolling
        if udid in enrolled_devices:
            del enrolled_devices[udid]
        logger.info(f"Device {udid} checked out")
        return Response(status_code=200)
    
    return Response(status_code=400)


@app.put("/mdm/command")
async def mdm_command(request: Request):
    """Handle MDM command responses and send pending commands"""
    body = await request.body()
    data = parse_plist(body)
    
    udid = data.get("UDID")
    status = data.get("Status")
    command_uuid = data.get("CommandUUID")
    
    logger.info(f"Command response - UDID: {udid}, Status: {status}, UUID: {command_uuid}")
    
    # Update device last seen
    if udid in enrolled_devices:
        enrolled_devices[udid]["last_seen"] = datetime.utcnow().isoformat()
    
    # Process command response
    if status == "Acknowledged":
        logger.info(f"Command {command_uuid} acknowledged by {udid}")
        # Process response data
        if "QueryResponses" in data:
            logger.info(f"Query responses: {data['QueryResponses']}")
    elif status == "Error":
        error_chain = data.get("ErrorChain", [])
        logger.error(f"Command {command_uuid} failed: {error_chain}")
    
    # Check for pending commands
    if udid in pending_commands and pending_commands[udid]:
        command = pending_commands[udid].pop(0)
        logger.info(f"Sending pending command to {udid}: {command['Command']['RequestType']}")
        return create_plist_response(command)
    
    # No pending commands
    return Response(status_code=200)


# ==================== Management API Endpoints ====================

@app.get("/api/devices")
async def list_devices():
    """List all enrolled devices"""
    return {"devices": list(enrolled_devices.values())}


@app.get("/api/devices/{udid}")
async def get_device(udid: str):
    """Get device details"""
    if udid not in enrolled_devices:
        raise HTTPException(status_code=404, detail="Device not found")
    return enrolled_devices[udid]


@app.post("/api/devices/{udid}/command")
async def send_command(udid: str, command: dict):
    """Queue a command for a device and send APNs notification"""
    
    if udid not in enrolled_devices:
        raise HTTPException(status_code=404, detail="Device not found")
    
    device = enrolled_devices[udid]
    command_uuid = str(uuid.uuid4())
    mdm_command = {
        "CommandUUID": command_uuid,
        "Command": command
    }
    
    if udid not in pending_commands:
        pending_commands[udid] = []
    
    pending_commands[udid].append(mdm_command)
    logger.info(f"Command queued for {udid}: {command.get('RequestType')}")
    
    # Send APNs notification to wake device
    push_result = await send_apns_notification(
        token=device["token"],
        push_magic=device["push_magic"],
        topic=MDM_CONFIG["topic"]
    )
    
    return {
        "status": "queued",
        "command_uuid": command_uuid,
        "apns_sent": push_result
    }


@app.post("/api/devices/{udid}/device-info")
async def request_device_info(udid: str):
    """Request device information"""
    queries = [
        "DeviceName", "OSVersion", "BuildVersion", "ModelName",
        "Model", "ProductName", "SerialNumber", "DeviceCapacity",
        "AvailableDeviceCapacity", "BatteryLevel", "UDID",
        "IsSupervised", "IsDeviceLocatorServiceEnabled"
    ]
    
    command = {
        "RequestType": "DeviceInformation",
        "Queries": queries
    }
    
    return await send_command(udid, command)


@app.post("/api/devices/{udid}/install-profile")
async def install_profile(udid: str, profile: dict):
    """Install a configuration profile"""
    command = {
        "RequestType": "InstallProfile",
        "Payload": plistlib.dumps(profile)
    }
    
    return await send_command(udid, command)


@app.post("/api/devices/{udid}/device-lock")
async def device_lock(udid: str, message: Optional[str] = None, phone_number: Optional[str] = None):
    """Lock a device"""
    command = {
        "RequestType": "DeviceLock"
    }
    
    if message:
        command["Message"] = message
    if phone_number:
        command["PhoneNumber"] = phone_number
    
    return await send_command(udid, command)


# ==================== Lost Mode API Endpoints ====================

@app.post("/api/devices/{udid}/lost-mode/enable")
async def enable_lost_mode(
    udid: str,
    message: str,
    phone_number: str,
    footnote: Optional[str] = None
):
    """Enable Lost Mode on a device"""
    if udid not in enrolled_devices:
        raise HTTPException(status_code=404, detail="Device not found")
    
    command = {
        "RequestType": "EnableLostMode",
        "Message": message,
        "PhoneNumber": phone_number
    }
    
    if footnote:
        command["Footnote"] = footnote
    
    # Update device status
    enrolled_devices[udid]["lost_mode_enabled"] = True
    enrolled_devices[udid]["lost_mode_message"] = message
    enrolled_devices[udid]["lost_mode_phone"] = phone_number
    
    result = await send_command(udid, command)
    logger.info(f"Lost Mode enabled for device {udid}")
    
    return result


@app.post("/api/devices/{udid}/lost-mode/disable")
async def disable_lost_mode(udid: str):
    """Disable Lost Mode on a device"""
    if udid not in enrolled_devices:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if not enrolled_devices[udid].get("lost_mode_enabled"):
        raise HTTPException(status_code=400, detail="Lost Mode is not enabled")
    
    command = {
        "RequestType": "DisableLostMode"
    }
    
    # Update device status
    enrolled_devices[udid]["lost_mode_enabled"] = False
    enrolled_devices[udid].pop("lost_mode_message", None)
    enrolled_devices[udid].pop("lost_mode_phone", None)
    
    result = await send_command(udid, command)
    logger.info(f"Lost Mode disabled for device {udid}")
    
    return result


@app.get("/api/devices/{udid}/lost-mode/location")
async def get_lost_mode_location(udid: str):
    """Request device location (requires Lost Mode or location services)"""
    if udid not in enrolled_devices:
        raise HTTPException(status_code=404, detail="Device not found")
    
    command = {
        "RequestType": "DeviceLocation"
    }
    
    result = await send_command(udid, command)
    logger.info(f"Location requested for device {udid}")
    
    return result


@app.post("/api/devices/{udid}/lost-mode/play-sound")
async def play_lost_mode_sound(udid: str):
    """Play sound on lost device"""
    if udid not in enrolled_devices:
        raise HTTPException(status_code=404, detail="Device not found")
    
    command = {
        "RequestType": "PlayLostModeSound"
    }
    
    result = await send_command(udid, command)
    logger.info(f"Lost Mode sound requested for device {udid}")
    
    return result

@app.delete("/api/devices/{udid}")
async def unenroll_device(udid: str):
    """Remove device from MDM"""
    if udid not in enrolled_devices:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Send RemoveProfile command
    command = {
        "RequestType": "RemoveProfile",
        "Identifier": "com.yourorg.mdm"
    }
    
    await send_command(udid, command)
    
    return {"status": "unenrollment_initiated"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)