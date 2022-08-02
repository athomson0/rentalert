#!/bin/bash
pip install -r requirements.txt

read -p "Which email address should alerts be sent to?: " RECIPIENT
read -p "Enter Gmail username: " GMAIL_USERNAME
read -p "Enter Gmail password (use an app password - https://support.google.com/mail/answer/185833): " GMAIL_PASSWORD

sed -i "s/RECIPIENT=''/RECIPIENT='$RECIPIENT'/" config.py.dist
sed -i "s/EMAIL_USERNAME=''/EMAIL_USERNAME='$GMAIL_USERNAME'/" config.py.dist
sed -i "s/EMAIL_PASSWORD=''/EMAIL_PASSWORD='$GMAIL_PASSWORD'/" config.py.dist
mv config.py.dist config.py

crontab -l | { cat; echo "*/10 * * * * python3 $PWD/__main__.py 2>$PWD/error.log"; } | crontab -

echo "Cronjob set up. Please run: python3 $PWD/__main__.py once manually to ensure that the script works properly."