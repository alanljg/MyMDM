#!/bin/bash
# Script to help set up MDM certificates

set -e  # Exit on error

echo "=============================="
echo "MDM Certificate Setup Helper"
echo "=============================="
echo ""

# Create certs directory
mkdir -p certs

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# Main menu
echo "Select an option:"
echo "1. Generate Vendor MDM CSR and Private Key"
echo "2. Convert APNs Push Certificate (.p12 to PEM)"
echo "3. Verify Certificate Setup"
echo "4. View Certificate Information"
echo "5. Complete Setup (All Steps)"
echo ""
read -p "Enter option (1-5): " option

case $option in
    1)
        echo ""
        echo "=== Generating Vendor MDM CSR and Private Key ==="
        echo ""
        
        # Get organization details
        read -p "Organization Name (e.g., Your Company Inc.): " org_name
        read -p "Common Name (e.g., Your MDM Server): " common_name
        read -p "Email Address: " email
        read -p "Country Code (2 letters, e.g., US): " country
        read -p "State/Province: " state
        read -p "City/Locality: " city
        
        # Optional organizational unit
        read -p "Organizational Unit (optional, press enter to skip): " org_unit
        
        echo ""
        print_info "Generating 2048-bit RSA private key..."
        
        # Generate private key
        openssl genrsa -out certs/vendor_key.pem 2048
        
        print_success "Private key generated: certs/vendor_key.pem"
        
        # Create OpenSSL config for CSR
        cat > certs/csr_config.txt <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[dn]
C=$country
ST=$state
L=$city
O=$org_name
CN=$common_name
emailAddress=$email
EOF

        # Add OU if provided
        if [ ! -z "$org_unit" ]; then
            sed -i.bak "/emailAddress/i OU=$org_unit" certs/csr_config.txt
        fi

        # Add extensions
        cat >> certs/csr_config.txt <<EOF

[v3_req]
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth, clientAuth
EOF

        print_info "Generating Certificate Signing Request (CSR)..."
        
        # Generate CSR
        openssl req -new -key certs/vendor_key.pem \
            -out certs/vendor_csr.pem \
            -config certs/csr_config.txt
        
        print_success "CSR generated: certs/vendor_csr.pem"
        
        echo ""
        echo "=== Next Steps ==="
        print_info "1. Submit certs/vendor_csr.pem to Apple for MDM vendor certificate"
        print_info "2. Once approved, download the certificate from Apple"
        print_info "3. Save the certificate as certs/vendor_cert.pem"
        print_info "4. Keep certs/vendor_key.pem secure (this is your private key)"
        
        echo ""
        print_info "CSR Content (copy this to Apple's portal if needed):"
        echo "---BEGIN CSR---"
        cat certs/vendor_csr.pem
        echo "---END CSR---"
        
        # Clean up temp files
        rm -f certs/csr_config.txt.bak
        ;;
        
    2)
        echo ""
        echo "=== Converting APNs Push Certificate ==="
        echo ""
        
        read -p "Path to APNs .p12 file: " p12_path
        
        if [ ! -f "$p12_path" ]; then
            print_error "File not found: $p12_path"
            exit 1
        fi
        
        print_info "Converting certificate..."
        
        # Extract certificate
        openssl pkcs12 -in "$p12_path" -out certs/mdm_push_cert.pem -nodes -clcerts
        
        # Extract private key
        openssl pkcs12 -in "$p12_path" -out certs/mdm_push_key.pem -nodes -nocerts
        
        print_success "APNs certificate: certs/mdm_push_cert.pem"
        print_success "APNs private key: certs/mdm_push_key.pem"
        ;;
        
    3)
        echo ""
        echo "=== Verifying Certificate Setup ==="
        echo ""
        
        all_good=true
        
        # Check Vendor Certificate
        if [ -f "certs/vendor_cert.pem" ]; then
            print_success "Vendor certificate found"
        else
            print_error "Vendor certificate missing (certs/vendor_cert.pem)"
            all_good=false
        fi
        
        # Check Vendor Key
        if [ -f "certs/vendor_key.pem" ]; then
            print_success "Vendor private key found"
            
            # Verify key format
            if openssl rsa -in certs/vendor_key.pem -check -noout 2>/dev/null; then
                print_success "Vendor key is valid"
            else
                print_error "Vendor key is invalid or corrupted"
                all_good=false
            fi
        else
            print_error "Vendor private key missing (certs/vendor_key.pem)"
            all_good=false
        fi
        
        # Check Vendor CSR
        if [ -f "certs/vendor_csr.pem" ]; then
            print_success "Vendor CSR found"
        else
            print_info "Vendor CSR not found (optional)"
        fi
        
        # Check APNs Certificate
        if [ -f "certs/mdm_push_cert.pem" ]; then
            print_success "APNs push certificate found"
        else
            print_error "APNs push certificate missing (certs/mdm_push_cert.pem)"
            all_good=false
        fi
        
        # Check APNs Key
        if [ -f "certs/mdm_push_key.pem" ]; then
            print_success "APNs push private key found"
            
            # Verify key format
            if openssl rsa -in certs/mdm_push_key.pem -check -noout 2>/dev/null; then
                print_success "APNs key is valid"
            else
                print_error "APNs key is invalid or corrupted"
                all_good=false
            fi
        else
            print_error "APNs push private key missing (certs/mdm_push_key.pem)"
            all_good=false
        fi
        
        echo ""
        if [ "$all_good" = true ]; then
            print_success "All required certificates are present and valid!"
        else
            print_error "Some certificates are missing or invalid. Please complete the setup."
        fi
        ;;
        
    4)
        echo ""
        echo "=== Certificate Information ==="
        echo ""
        
        if [ -f "certs/vendor_cert.pem" ]; then
            echo "--- Vendor Certificate ---"
            openssl x509 -in certs/vendor_cert.pem -text -noout | grep -A2 "Subject:\|Issuer:\|Not Before\|Not After"
            echo ""
        fi
        
        if [ -f "certs/vendor_csr.pem" ]; then
            echo "--- Vendor CSR ---"
            openssl req -in certs/vendor_csr.pem -text -noout | grep -A5 "Subject:"
            echo ""
        fi
        
        if [ -f "certs/mdm_push_cert.pem" ]; then
            echo "--- APNs Push Certificate ---"
            openssl x509 -in certs/mdm_push_cert.pem -text -noout | grep -A2 "Subject:\|Issuer:\|Not Before\|Not After"
            echo ""
        fi
        
        if [ -f "certs/vendor_key.pem" ]; then
            echo "--- Vendor Private Key Info ---"
            openssl rsa -in certs/vendor_key.pem -text -noout | grep "Private-Key:"
            echo ""
        fi
        
        if [ -f "certs/mdm_push_key.pem" ]; then
            echo "--- APNs Private Key Info ---"
            openssl rsa -in certs/mdm_push_key.pem -text -noout | grep "Private-Key:"
            echo ""
        fi
        ;;
        
    5)
        echo ""
        echo "=== Complete Setup Wizard ==="
        echo ""
        
        # Step 1: Generate Vendor CSR
        print_info "Step 1: Generating Vendor MDM CSR and Private Key"
        echo ""
        
        read -p "Organization Name: " org_name
        read -p "Common Name: " common_name
        read -p "Email Address: " email
        read -p "Country Code (2 letters): " country
        read -p "State/Province: " state
        read -p "City/Locality: " city
        
        openssl genrsa -out certs/vendor_key.pem 2048
        
        cat > certs/csr_config.txt <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[dn]
C=$country
ST=$state
L=$city
O=$org_name
CN=$common_name
emailAddress=$email

[v3_req]
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth, clientAuth
EOF

        openssl req -new -key certs/vendor_key.pem \
            -out certs/vendor_csr.pem \
            -config certs/csr_config.txt
        
        print_success "Vendor CSR and key generated"
        
        echo ""
        print_info "CSR generated. Submit this to Apple:"
        cat certs/vendor_csr.pem
        
        echo ""
        read -p "After receiving certificate from Apple, press Enter to continue..."
        read -p "Path to vendor certificate from Apple: " vendor_cert_path
        
        if [ -f "$vendor_cert_path" ]; then
            cp "$vendor_cert_path" certs/vendor_cert.pem
            print_success "Vendor certificate installed"
        else
            print_error "Certificate file not found. Please install manually."
        fi
        
        # Step 2: APNs Certificate
        echo ""
        print_info "Step 2: Converting APNs Push Certificate"
        echo ""
        
        read -p "Path to APNs .p12 file: " p12_path
        
        if [ -f "$p12_path" ]; then
            openssl pkcs12 -in "$p12_path" -out certs/mdm_push_cert.pem -nodes -clcerts
            openssl pkcs12 -in "$p12_path" -out certs/mdm_push_key.pem -nodes -nocerts
            print_success "APNs certificates installed"
        else
            print_error "APNs file not found. Please convert manually."
        fi
        
        echo ""
        print_success "Setup complete!"
        
        # Run verification
        echo ""
        $0 3
        
        rm -f certs/csr_config.txt.bak
        ;;
        
    *)
        print_error "Invalid option"
        exit 1
        ;;
esac

echo ""
echo "=============================="
print_success "Done!"
echo "=============================="