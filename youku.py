import requests
import base64
import json
import urllib
import m3u8
import re
import os
import signal
import subprocess
from pyasstosrt import Subtitle
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH
from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from seleniumwire.utils import decode as sw_decode
import seleniumwire.undetected_chromedriver.v2 as uc
from bs4 import BeautifulSoup
from time import sleep
import unicodedata

#Config
MyWVD = './WVD.wvd'

def signal_handler(sig, frame):
    s_exit()

signal.signal(signal.SIGINT, signal_handler)

def do_cdm(manifest_url, data):
    fkeys = ""

    try:
        manifest = m3u8.load(manifest_url) 
    except:
        print('Error loading manifest')
        return
    
    for key in manifest.keys:
        if key and 'base64' in key.uri:
            pssh = PSSH(key.uri.split(',')[-1])

    if pssh is None:
        print('Error getting pssh')
        s_exit()

    #CDM processing

    device = Device.load(MyWVD)
    cdm = Cdm.from_device(device)
    session_id = cdm.open()
    challenge = cdm.get_license_challenge(session_id, pssh)

    headers = {
        'content-type': 'application/x-www-form-urlencoded',
    }
    
    data += '&licenseRequest=' + urllib.parse.quote(base64.b64encode(challenge).decode())

    licence = requests.post('https://drm-license.youku.tv/ups/drm.json', headers=headers, data=data)
    licence.raise_for_status()
    
    cdm.parse_license(session_id, json.loads(licence.content)['data'])

    for key in cdm.get_keys(session_id):
        if key.type != 'SIGNING':
            fkeys += key.kid.hex + ":" + key.key.hex()
            
    cdm.close(session_id)

    return fkeys.strip()
   
def slugify(value, allow_unicode=False):
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '.', value).strip('-_')
   
def get_inner_m3u8(m3u8_url):
    try:
        manifest = m3u8.load(m3u8_url) 
    except:
        print('Error loading m3u8')
        return
        
    return manifest.media.uri[0]
   
def selenium_init():
    print('Initializing selenium')

    options = uc.ChromeOptions()
    options.page_load_strategy = 'eager'
    
    options.add_argument('--user-data-dir=' + os.path.abspath(os.getcwd()) + '\\UserData')
    options.add_argument('--headless')
    options.add_argument('--disable-features=Translate')
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--log-level=3')
    driver = uc.Chrome(options=options)
    
    return driver
   
def extract_acs(driver):
    print('Getting acs from url')

    body = None
    
    for request in driver.requests:
        if 'mtop.youku.play.ups.appinfo.get' in request.url:
            body = sw_decode(request.response.body, request.response.headers.get('Content-Encoding', 'identity')).decode()
            del driver.requests
            
    if body is None:
        print('Failed to extract acs response from url, please try again')
        s_exit()

    body = json.loads(re.search(r'mtopjsonp[0-9]\((.*?)\)', body).group(1))

    try:
        stream = body['data']['data']['stream']
    except:
        print('You don\'t have permission to play this video')
        print('Are you logged in with a VIP account?')
        return


    i = -1
    while abs(i) <= len(stream):
        if '#EXTM3U' not in stream[i]['m3u8_url']:
            maxres = stream[i]
            break;
        i-=1
 
    #Test low res download
    #maxres = stream[0]
    
    if maxres is None:
        print('Failed getting maxres')
        s_exit()
    
    r = {}
    
    r['m3u8_url'] = maxres['m3u8_url']
    
    if 'uri' in maxres['stream_ext']:
        r['license_data'] = maxres['stream_ext']['uri'].replace('cbcs', 'widevine').replace('https://drm-license.youku.tv/ups/drm.json?', '')
    else:
        r['license_data'] = None
        
    subs = []
    subtitles = body['data']['data']['subtitle']
    for s in subtitles:
        t = {}
        t['lang'] = s['subtitle_info_code'][0]
        t['url'] = s['url']
        subs.append(t)
    
    r['subtitles'] = subs
    
    return r
 
def get_episodes(driver):

    episode_class = BeautifulSoup(driver.page_source, 'html.parser').find("div", {"class": "new-box-anthology-items"})
    children = episode_class.findChildren("a" , recursive=False)
    
    
    if len(children) == 0:
        episode_class = BeautifulSoup(driver.page_source, 'html.parser').find("div", {"class": "anthology-content"})
        children = episode_class.findChildren("a" , recursive=True)
    
    r = []
    
    if len(children) == 1:
        return r
    
    for child in children:
        i = {}
        
        try:
            i['title'] = child['title']
        except:
            i['title'] = child.find("div", {"class": "new-title"}).text

        i['href'] = child['href']
        r.append(i)
        
    return r
 
def s_request(url, driver):
    driver.get(url)
    
    try:
        driver.wait_for_request('mtop.youku.play.ups.appinfo.get', timeout=60)
    except:
        print('Page load took too much time, please try again')
        s_exit()
    
    return driver

def get_title(driver):
    title_class = BeautifulSoup(driver.page_source, 'html.parser').find("h3", {"class": "new-title-name"})
    return title_class.text

def s_exit():
    print('\nBye :)')
    global driver
    driver.quit()
    quit()

def dl_media(driver, foldername, filename):
    acs = extract_acs(driver)
    
    foldername = slugify(foldername)
    filename = slugify(filename)
    
    if acs is None:
        return
    
    
    m3u8_url = acs['m3u8_url']
    license_data = acs['license_data']
    
    proc_list = ['N_m3u8DL-RE.exe', '--save-dir', 'Downloads/' + foldername, '--tmp-dir', 'Temp/', '--save-name', filename, '-sv', 'best', '-sa', 'best', m3u8_url, '-M', 'mp4']
    
    if license_data is not None:
        inner_m3u8 = get_inner_m3u8(m3u8_url)

        key = do_cdm(inner_m3u8, license_data)

        proc_list[1:1] = ['--key', key]

        print(key)
    else:
        print('No drm found')
        
    print('Downloading')
    
    subprocess.run(proc_list)
    
    print('Downloading subtitles')
    
    subtitles = acs['subtitles']
    for s in subtitles:
        iso_code = s['lang']
        sub_url = s['url']
        
        subpath = '.\\Downloads\\' + foldername + '\\' + filename + ' ' + iso_code + '.ass'
        
        f = open(subpath, "w", encoding="utf-8")
        f.write(requests.get(sub_url).text)
        f.close()
        
        #Convert to sr
        sub = Subtitle(subpath)
        sub.export()
        os.remove(subpath)
        
    print('Done')
    

def suppress_exception_in_del(uc):
    old_del = uc.Chrome.__del__

    def new_del(self) -> None:
        try:
            old_del(self)
        except:
            pass
    
    setattr(uc.Chrome, '__del__', new_del)

suppress_exception_in_del(uc)

driver = selenium_init()

url = input('Enter youku.tv url: ')

print('Opening provided url')

s_request(url, driver)

main_title = get_title(driver)
print(main_title)

episodes = get_episodes(driver)

if len(episodes) > 0:
    print('Detected series')
    
    c = input('Do you want to download the entire series? (y/n): ')
    
    if c.lower() != 'y':
        print('Single episode download selected')
        dl_media(driver, main_title, main_title)
        s_exit()

    for e in episodes:
        print(e['title'])
        s_request(e['href'], driver)
        dl_media(driver, main_title, e['title'])
        
    s_exit()
else:
    print('Detected single')
    dl_media(driver, main_title, main_title)
    s_exit()
