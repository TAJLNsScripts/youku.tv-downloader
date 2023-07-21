# youku.tv-downloader
Used to download movies and series from youku.tv

Prerequisites:
- Pywidevine cdm file in .wvd format
- Google Chrome installed
- youku.tv VIP account (optional, for VIP content)

Usage:
- pip install -r requirements.txt
- python youku.py

VIP content:
1. Log into your youku.tv account in Google Chrome
2. Navigate to your Google Chrome User Data folder.
   Windows path: C:\Users\%USERNAME%\AppData\Local\Google\Chrome\User Data
3. Copy everything in the folder to UserData folder next to your youku.py
4. You should now be able to download VIP content
