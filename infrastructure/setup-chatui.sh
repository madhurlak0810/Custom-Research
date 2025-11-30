#!/bin/bash

# Update system
yum update -y

# Install required packages
yum install -y httpd git

# Start and enable Apache
systemctl start httpd
systemctl enable httpd

# Clone the repository
cd /var/www/html
rm -rf *
git clone https://github.com/madhurlak0810/Custom-Research.git .

# Set proper permissions
chmod -R 755 /var/www/html
chown -R apache:apache /var/www/html

# Create redirect from root to chat_ui
cat > /var/www/html/index.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>Research Assistant</title>
    <meta http-equiv="refresh" content="0; url=/chat_ui/">
</head>
<body>
    <p>Redirecting to <a href="/chat_ui/">Chat UI</a>...</p>
</body>
</html>
EOF

# Get the API Gateway endpoint from instance metadata/tags
# This will be replaced by CDK with the actual endpoint
API_ENDPOINT="API_ENDPOINT_PLACEHOLDER"

# Update the JavaScript file with the correct API endpoint
if [ "$API_ENDPOINT" != "API_ENDPOINT_PLACEHOLDER" ]; then
    # Remove any trailing slashes and update the script
    API_ENDPOINT=$(echo "$API_ENDPOINT" | sed 's/\/$//')
    sed -i "s|https://your-api-endpoint/prod|$API_ENDPOINT|g" /var/www/html/chat_ui/script.js
    
    # Also update any hardcoded localhost references
    sed -i "s|http://localhost:8000||g" /var/www/html/chat_ui/README.md
    
    # Create a configuration file for the UI
    cat > /var/www/html/chat_ui/config.js << EOF
// Auto-generated configuration
window.CONFIG = {
    apiEndpoint: '$API_ENDPOINT',
    autoLoad: true
};
EOF
fi

# Configure Apache
cat > /etc/httpd/conf.d/chatui.conf << 'EOF'
<VirtualHost *:80>
    DocumentRoot /var/www/html
    
    # Enable CORS for API calls
    Header always set Access-Control-Allow-Origin "*"
    Header always set Access-Control-Allow-Methods "GET, POST, OPTIONS"
    Header always set Access-Control-Allow-Headers "Content-Type, Authorization"
    
    # Cache static files
    <LocationMatch "\.(css|js|png|jpg|jpeg|gif|ico|svg)$">
        ExpiresActive On
        ExpiresDefault "access plus 1 month"
    </LocationMatch>
    
    # Enable gzip compression
    LoadModule deflate_module modules/mod_deflate.so
    <Location />
        SetOutputFilter DEFLATE
        SetEnvIfNoCase Request_URI \
            \.(?:gif|jpe?g|png)$ no-gzip dont-vary
        SetEnvIfNoCase Request_URI \
            \.(?:exe|t?gz|zip|bz2|sit|rar)$ no-gzip dont-vary
    </Location>
    
    # Security headers
    Header always set X-Content-Type-Options nosniff
    Header always set X-Frame-Options DENY
    Header always set X-XSS-Protection "1; mode=block"
    
    ErrorLog /var/log/httpd/chatui_error.log
    CustomLog /var/log/httpd/chatui_access.log combined
</VirtualHost>
EOF

# Restart Apache to apply configuration
systemctl restart httpd

# Create a simple health check endpoint
mkdir -p /var/www/html/health
cat > /var/www/html/health/index.html << 'EOF'
{
  "status": "healthy",
  "timestamp": "TIMESTAMP_PLACEHOLDER",
  "service": "chat-ui"
}
EOF

# Replace timestamp
sed -i "s/TIMESTAMP_PLACEHOLDER/$(date -u +%Y-%m-%dT%H:%M:%SZ)/" /var/www/html/health/index.html

# Log completion
echo "Chat UI setup completed at $(date)" >> /var/log/chatui-setup.log