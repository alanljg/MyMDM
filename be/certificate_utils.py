import os
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.hazmat.backends import default_backend
import plistlib

def load_vendor_certificate():
    '''Load MDM vendor certificate and private key'''
    cert_path = os.getenv('MDM_VENDOR_CERT_PATH', './certs/vendor_cert.pem')
    key_path = os.getenv('MDM_VENDOR_KEY_PATH', './certs/vendor_key.pem')
    
    with open(cert_path, 'rb') as f:
        cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())
    
    with open(key_path, 'rb') as f:
        key_data = f.read()
        key = serialization.load_pem_private_key(
            key_data,
            password=None,
            backend=default_backend()
        )
    
    return cert, key

def sign_profile(profile_dict):
    '''Sign a configuration profile with vendor certificate'''
    cert, key = load_vendor_certificate()
    
    # Convert profile to plist
    profile_data = plistlib.dumps(profile_dict)
    
    # Create PKCS#7 signature
    options = [pkcs7.PKCS7Options.Binary]
    
    signed_data = pkcs7.PKCS7SignatureBuilder().set_data(
        profile_data
    ).add_signer(
        cert, key, hashes.SHA256()
    ).sign(
        serialization.Encoding.DER,
        options
    )
    
    return signed_data

def verify_device_certificate(cert_data):
    '''Verify device certificate against MDM CA'''
    # Load the certificate
    cert = x509.load_der_x509_certificate(cert_data, default_backend())
    
    # In production, verify against your MDM CA
    # This is a placeholder for certificate validation
    return True