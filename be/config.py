from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Server
    server_url: str = "https://your-mdm-server.com"
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    
    # MDM
    mdm_organization: str = "Your Organization"
    mdm_topic: str = "com.apple.mgmt.External.your-uuid"
    
    # Security - Vendor Certificate
    mdm_vendor_cert_path: str = "./certs/vendor_cert.pem"
    mdm_vendor_key_path: str = "./certs/vendor_key.pem"
    
    # APNs Certificate
    apns_cert_path: str = "./certs/mdm_push_cert.pem"
    apns_key_path: str = "./certs/mdm_push_key.pem"
    apns_use_sandbox: bool = True
    
    # Database
    database_url: str = "sqlite:///./mdm.db"
    
    class Config:
        env_file = ".env"

settings = Settings()