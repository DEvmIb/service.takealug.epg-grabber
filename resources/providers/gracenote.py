# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import json
import os
import sys
import requests.cookies
import requests.adapters
import requests
import uuid
import time
from datetime import datetime
from datetime import timedelta
from resources.lib import xml_structure
from resources.lib import channel_selector
from resources.lib import mapper
from resources.lib import filesplit

provider = 'Gracenote (World)'
# we use lang per channel
#lang = 'multi'

ADDON = xbmcaddon.Addon(id="service.takealug.epg-grabber")
addon_name = ADDON.getAddonInfo('name')
addon_version = ADDON.getAddonInfo('version')
loc = ADDON.getLocalizedString
datapath = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
addon_path=xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
temppath = os.path.join(datapath, "temp")
provider_temppath = os.path.join(temppath, "gracenote")

## Enable Multithread
enable_multithread = True if ADDON.getSetting('enable_multithread').upper() == 'TRUE' else False
if enable_multithread:
    try:
        from multiprocessing import Process
    except:
        pass

gn_genres_json = os.path.join(addon_path, 'resources', 'config_files', 'gn_genres.json')
gn_channels_json = os.path.join(addon_path, 'resources', 'config_files', 'gn_channels.json')
gn_ratings_json = os.path.join(datapath, 'gn_ratings.json')
gn_ratings_dist = os.path.join(addon_path, 'resources', 'gn_ratings.json')

## Log Files
gracenote_genres_warnings_tmp = os.path.join(provider_temppath, 'gracenote_genres_warnings.txt')
gracenote_genres_warnings = os.path.join(temppath, 'gracenote_genres_warnings.txt')
gracenote_channels_warnings_tmp = os.path.join(provider_temppath, 'gracenote_channels_warnings.txt')
gracenote_channels_warnings = os.path.join(temppath, 'gracenote_channels_warnings.txt')




days_to_grab = int(ADDON.getSetting('gracenote_days_to_grab'))
episode_format = ADDON.getSetting('gracenote_episode_format')
channel_format = ADDON.getSetting('gracenote_channel_format')
genre_format = ADDON.getSetting('gracenote_genre_format')
gracenote_key = ADDON.getSetting('gracenote_key')
gracenote_rating_system = ADDON.getSetting('gracenote_rating_system')

if not os.path.exists(gn_ratings_json):
    done = xbmcvfs.copy(gn_ratings_dist, gn_ratings_json)
    ADDON.setSetting('gracenote_rating_system', 'Freiwillige Selbstkontrolle Fernsehen')
    gracenote_rating_system = 'Freiwillige Selbstkontrolle Fernsehen'
    
with open(gn_ratings_json, 'r', encoding='utf-8') as gn_rating_list_tmp:
        gn_ratings = json.load(gn_rating_list_tmp)
        
# Make a debug logger
def log(message, loglevel=xbmc.LOGDEBUG):
    xbmc.log('[{} {}] {}'.format(addon_name, addon_version, message), loglevel)


# Make OSD Notify Messages
OSD = xbmcgui.Dialog()

## Session UUID
mac = str(uuid.uuid4())
ter = str(uuid.uuid4())

def notify(title, message, icon=xbmcgui.NOTIFICATION_INFO):
    OSD.notification(title, message, icon)

def get_epgLength(days_to_grab):
    # Calculate Date and Time
    today = datetime.today()
    calc_today = datetime(today.year, today.month, today.day, hour=00, minute=00, second=1)

    calc_then = datetime(today.year, today.month, today.day, hour=23, minute=59, second=59)
    calc_then += timedelta(days=days_to_grab)

    #2025-08-14T06:00Z
    starttime = calc_today.strftime("%Y-%m-%dT%H:%MZ")
    endtime = calc_then.strftime("%Y-%m-%dT%H:%MZ")

    return starttime, endtime

## Channel Files
gracenote_base = os.path.join(datapath,  'gracenote.json')
gracenote_dist = os.path.join(addon_path, 'resources', 'gracenote.json')
gracenote_chlist_provider_tmp = os.path.join(provider_temppath, 'chlist_gracenote_provider_tmp.json')
gracenote_chlist_provider = os.path.join(provider_temppath, 'chlist_gracenote_provider.json')
gracenote_chlist_selected = os.path.join(datapath, 'chlist_gracenote_selected.json')

if not os.path.isfile(gracenote_base):
    # todo try
    done = xbmcvfs.copy(gracenote_dist, gracenote_base)

## Get channel list(url)
def get_channellist():
    if not os.path.isfile(gracenote_base):
        # todo try
        done = xbmcvfs.copy(gracenote_dist, gracenote_base)

    with open(gracenote_base, 'r', encoding='utf-8') as provider_list_tmp:
        gracenote_channels = json.load(provider_list_tmp)

    # Create empty new hznDE_chlist_provider
    with open(gracenote_chlist_provider, 'w', encoding='utf-8') as provider_list:
        provider_list.write(json.dumps({"channellist": []}))

    ch_title = ''

    # Load New Channellist from Provider
    with open(gracenote_chlist_provider, encoding='utf-8') as provider_list:
        data = json.load(provider_list)

        temp = data['channellist']

        for channels in gracenote_channels['channellist']:
            ch_id = channels['contentId']
            ch_title = channels['name']
            ch_lang = channels['lang']
            for image in channels['pictures']:
                hdimage = image['href']
            # channel to be appended
            y = {"contentId": ch_id,
                 "name": ch_title,
                 "lang": ch_lang,
                 "pictures": [{"href": hdimage}]}

            # appending channels to data['channellist']
            temp.append(y)

    #Save New Channellist from Provider
    with open(gracenote_chlist_provider, 'w', encoding='utf-8') as provider_list:
        json.dump(data, provider_list, indent=4)

def select_channels():
    ## Create Provider Temppath if not exist
    if not os.path.exists(provider_temppath):
        os.makedirs(provider_temppath)

    ## Create empty (Selected) Channel List if not exist
    if not os.path.isfile(gracenote_chlist_selected):
        with open((gracenote_chlist_selected), 'w', encoding='utf-8') as selected_list:
            selected_list.write(json.dumps({"channellist": []}))

    ## Download chlist_magenta_provider.json
    get_channellist()
    dialog = xbmcgui.Dialog()

    with open(gracenote_chlist_provider, 'r', encoding='utf-8') as o:
        provider_list = json.load(o)

    with open(gracenote_chlist_selected, 'r', encoding='utf-8') as s:
        selected_list = json.load(s)

    ## Start Channel Selector
    user_select = channel_selector.select_channels(provider, provider_list, selected_list)

    if user_select is not None:
        with open(gracenote_chlist_selected, 'w', encoding='utf-8') as f:
            json.dump(user_select, f, indent=4)
        if os.path.isfile(gracenote_chlist_selected):
            valid = check_selected_list()
            if valid is True:
                ok = dialog.ok(provider, loc(32402))
                if ok:
                    log(loc(32402), xbmc.LOGINFO)
            elif valid is False:
                log(loc(32403), xbmc.LOGINFO)
                yn = OSD.yesno(provider, loc(32403))
                if yn:
                    select_channels()
                else:
                    xbmcvfs.delete(gracenote_chlist_selected)
                    exit()
    else:
        valid = check_selected_list()
        if valid is True:
            ok = dialog.ok(provider, loc(32404))
            if ok:
                log(loc(32404), xbmc.LOGINFO)
        elif valid is False:
            log(loc(32403), xbmc.LOGINFO)
            yn = OSD.yesno(provider, loc(32403))
            if yn:
                select_channels()
            else:
                xbmcvfs.delete(gracenote_chlist_selected)
                exit()
                
def select_rating():
    dialog = xbmcgui.Dialog()
    items = list()
    
    #selected = list()
    index = 0
    index_sel = 0
    gn_ratings_sorted = {k: gn_ratings[k] for k in sorted(gn_ratings)}
    for item in gn_ratings_sorted:
        if item == ADDON.getSetting('gracenote_rating_system'):
            index_sel=index
        descriptor = xbmcgui.ListItem(label=item)
        items.append(descriptor)
        index += 1
        
    selected = xbmcgui.Dialog().select('{} ]-{}-['.format(provider,loc(32620)), items, preselect=index_sel)
    if selected > -1:
        log(f'selected: {items[selected].getLabel()}',2)
        log(f'selected: {selected}',2)
        ADDON.setSetting('gracenote_rating_system', items[selected].getLabel())

def check_selected_list():
    check = 'invalid'
    with open(gracenote_chlist_selected, 'r', encoding='utf-8') as c:
        selected_list = json.load(c)
    for user_list in selected_list['channellist']:
        if 'contentId' in user_list:
            check = 'valid'
    if check == 'valid':
        return True
    else:
        return False

def download_multithread(thread_temppath, download_threads):
    # delete old broadcast files if exist
    for f in os.listdir(provider_temppath):
        if f.endswith('_broadcast.json'):
            xbmcvfs.delete(os.path.join(provider_temppath, f))

  
    list = os.path.join(provider_temppath, 'list.txt')
    splitname = os.path.join(thread_temppath, 'chlist_gracenote_selected')
    starttime, endtime = get_epgLength(days_to_grab)

    with open(gracenote_chlist_selected, 'r', encoding='utf-8') as s:
        selected_list = json.load(s)
    if filesplit.split_chlist_selected(thread_temppath, gracenote_chlist_selected, splitname, download_threads, enable_multithread):
        multi = True
        needed_threads = sum([len(files) for r, d, files in os.walk(thread_temppath)])
        items_to_download = str(len(selected_list['channellist']))
        log('{} {} {} '.format(provider, items_to_download, loc(32361)), xbmc.LOGINFO)
        pDialog = xbmcgui.DialogProgressBG()
        log('{} Multithread({}) Mode'.format(provider, needed_threads), xbmc.LOGINFO)
        pDialog.create('{} {} '.format(loc(32500), provider), '{} {}'.format('100', loc(32501)))

        jobs = []
        for thread in range(0, int(needed_threads)):
            p = Process(target=download_thread, args=('{}_{}.json'.format(splitname, int(thread)), multi, list, starttime, endtime, ))
            jobs.append(p)
            p.start()
        for j in jobs:
            while j.is_alive():
                xbmc.sleep(100)
                try:
                    last_line = ''
                    with open(list, 'r', encoding='utf-8') as f:
                        last_line = f.readlines()[-1]
                except:
                    pass
                items = sum(1 for f in os.listdir(provider_temppath) if f.endswith('_broadcast.json'))
                percent_remain = int(100) - int(items) * int(100) / int(items_to_download)
                percent_completed = int(100) * int(items) / int(items_to_download)
                pDialog.update(int(percent_completed), '{} {} '.format(loc(32500), last_line), '{} {} {}'.format(int(percent_remain), loc(32501), provider))
                if int(items) == int(items_to_download):
                    log('{} {}'.format(provider, loc(32363)), xbmc.LOGINFO)
                    break
            j.join()
        pDialog.close()
        for file in os.listdir(thread_temppath): xbmcvfs.delete(os.path.join(thread_temppath, file))

    else:
        multi = False
        log('{} {} '.format(provider, 'Can`t download in Multithreading mode, loading single...'), xbmc.LOGINFO)
        download_thread(gracenote_chlist_selected, multi, list, starttime, endtime)

def download_thread(gracenote_chlist_selected, multi, list, starttime, endtime):
    requests.adapters.DEFAULT_RETRIES = 5
    session = requests.Session()

    with open(gracenote_chlist_selected, 'r', encoding='utf-8') as s:
        selected_list = json.load(s)

    if not multi:
        items_to_download = str(len(selected_list['channellist']))
        log('{} {} {} '.format(provider, items_to_download, loc(32361)), xbmc.LOGINFO)
        pDialog = xbmcgui.DialogProgressBG()
        pDialog.create('{} {} '.format(loc(32500), provider), '{} {}'.format('100', loc(32501)))

    for user_item in selected_list['channellist']:
        contentID = user_item['contentId']
        channel_name = user_item['name']

        response = session.get(f"http://data.tmsapi.com/v1.1/stations/{contentID}/airings?startDateTime={starttime}&endDateTime={endtime}&imageSize=Md&imageAspectTV=16x9&api_key={gracenote_key}")
        response.raise_for_status()
        gn_data = response.json()
        broadcast_files = os.path.join(provider_temppath, '{}_broadcast.json'.format(contentID))
        with open(broadcast_files, 'w', encoding='utf-8') as playbill:
            json.dump(gn_data, playbill)
        ## Create a List with downloaded channels
        last_channel_name = '{}\n'.format(channel_name)
        with open(list, 'a', encoding='utf-8') as f:
            f.write(last_channel_name)

        if not multi:
            items = sum(1 for f in os.listdir(provider_temppath) if f.endswith('_broadcast.json'))
            percent_remain = int(100) - int(items) * int(100) / int(items_to_download)
            percent_completed = int(100) * int(items) / int(items_to_download)
            pDialog.update(int(percent_completed), '{} {} '.format(loc(32500), channel_name), '{} {} {}'.format(int(percent_remain), loc(32501), provider))
            if int(items) == int(items_to_download):
                log('{} {}'.format(provider, loc(32363)), xbmc.LOGINFO)
                break
    if not multi:
        pDialog.close()


def create_xml_channels():
    log('{} {}'.format(provider,loc(32362)), xbmc.LOGINFO)

    with open(gracenote_chlist_selected, 'r', encoding='utf-8') as c:
        selected_list = json.load(c)

    items_to_download = str(len(selected_list['channellist']))
    items = 0
    pDialog = xbmcgui.DialogProgressBG()
    pDialog.create('{} {} '.format(loc(32502),provider), '{} {}'.format('100',loc(32501)))

    ## Create XML Channels Provider information
    xml_structure.xml_channels_start(provider)

    for user_item in selected_list['channellist']:
        items += 1
        percent_remain = int(100) - int(items) * int(100) / int(items_to_download)
        percent_completed = int(100) * int(items) / int(items_to_download)
        channel_name = user_item['name']
        channel_icon = user_item['pictures'][0]['href']
        channel_id = channel_name
        lang = user_item['lang']
        pDialog.update(int(percent_completed), '{} {} '.format(loc(32502),channel_name),'{} {} {}'.format(int(percent_remain),loc(32501),provider))
        if str(percent_completed) == str(100):
            log('{} {}'.format(provider,loc(32364)), xbmc.LOGINFO)

        ## Map Channels
        if not channel_id == '':
            channel_id = mapper.map_channels(channel_id, channel_format, gn_channels_json, gracenote_channels_warnings_tmp, lang)

        ## Create XML Channel Information with provided Variables
        xml_structure.xml_channels(channel_name, channel_id, channel_icon, lang)
    pDialog.close()


def create_xml_broadcast(enable_rating_mapper, thread_temppath, download_threads):

    download_multithread(thread_temppath, download_threads)
    log('{} {}'.format(provider, loc(32365)), xbmc.LOGINFO)

    with open(gracenote_chlist_selected, 'r', encoding='utf-8') as c:
        selected_list = json.load(c)

    items_to_download = str(len(selected_list['channellist']))
    items = 0
    pDialog = xbmcgui.DialogProgressBG()
    pDialog.create('{} {} '.format(loc(32503), provider), '{} Prozent verbleibend'.format('100'))

    ## Create XML Broadcast Provider information
    xml_structure.xml_broadcast_start(provider)

    for user_item in selected_list['channellist']:
        items += 1
        percent_remain = int(100) - int(items) * int(100) / int(items_to_download)
        percent_completed = int(100) * int(items) / int(items_to_download)
        contentID = user_item['contentId']
        channel_name = user_item['name']
        channel_id = channel_name
        lang = user_item['lang']
        pDialog.update(int(percent_completed), '{} {} '.format(loc(32503), channel_name), '{} {} {}'.format(int(percent_remain), loc(32501), provider))
        if str(percent_completed) == str(100):
            log('{} {}'.format(provider, loc(32366)), xbmc.LOGINFO)

        broadcast_files = os.path.join(provider_temppath, '{}_broadcast.json'.format(contentID))
        with open(broadcast_files, 'r', encoding='utf-8') as b:
            broadcastfiles = json.load(b)

        ### Map Channels
        if not channel_id == '':
            channel_id = mapper.map_channels(channel_id, channel_format, gn_channels_json, gracenote_channels_warnings_tmp, lang)
        try:
            for prg in broadcastfiles:
                epg=prg["program"]
                try:
                    item_title = epg['title']
                except (KeyError, IndexError):
                    item_title = ''
                try:
                    item_starttime = prg['startTime']
                except (KeyError, IndexError):
                    item_starttime = ''
                try:
                    item_endtime = prg['endTime']
                except (KeyError, IndexError):
                    item_endtime = ''
                try:
                    item_description = epg['shortDescription']
                except (KeyError, IndexError):
                    item_description = ''
                try:
                    item_long_description = epg['longDescription']
                except (KeyError, IndexError):
                    item_long_description = ''
                try:
                    item_country = epg['titleLang']
                except (KeyError, IndexError):
                    item_country = ''
                try:
                   item_picture = epg['preferredImage']['uri']
                except (KeyError, IndexError):
                    item_picture = ""    
                try:
                    item_subtitle = epg['episodeTitle']
                except (KeyError, IndexError):
                    item_subtitle = ''
                try:
                    items_genre = epg['genres']
                except (KeyError, IndexError):
                    items_genre = ''
                try:
                    item_date = epg['releaseYear']
                except (KeyError, IndexError):
                    item_date = ''
                try:
                    item_season = epg['seasonNum']
                except (KeyError, IndexError):
                    item_season = ''
                try:
                    item_episode = epg['episodeNum']
                except (KeyError, IndexError):
                    item_episode = ''
                try:
                    if epg['ratings']:
                        for ratings in epg['ratings']:
                            if not ratings["body"] in gn_ratings:
                                log("new rating system: {}".format(ratings["body"]), 2)
                                gn_ratings[ratings["body"]] = ratings["body"]
                                with open(gn_ratings_json, 'w', encoding='utf-8') as w:
                                    w.write(json.dumps(gn_ratings))
                            if ("Freiwillige" in ADDON.getSetting('gracenote_rating_system') and "Freiwillige" in ratings["body"]):
                                item_agerating = ratings["code"]
                                break
                            elif ratings["body"] == ADDON.getSetting('gracenote_rating_system'):
                                item_agerating = ratings["code"]
                                break
                        else:
                            item_agerating = ""
                except (KeyError, IndexError):
                    item_agerating = ''
                try:
                    # array
                    items_director = ','.join(epg['directors'])
                except (KeyError, IndexError):
                    items_director = ''
                # not available
                #try:
                #    items_producer = prg['cast']['producer']
                #except (KeyError, IndexError):
                items_producer = ''
                try:
                    # array
                    items_actor = ','.join(epg['topCast'])
                except (KeyError, IndexError):
                    items_actor = ''

                # Transform items to Readable XML Format
                item_starrating = ''
                #if not item_date == '':
                #    item_date = item_date.split('-')
                #    item_date = item_date[0]
                if (not item_starttime == '' and not item_endtime == ''):
                    # in: 2025-08-14T06:00Z
                    # out: 20250815091000 +0000
                    item_starttime = f"{item_starttime.replace('-','').replace(':','').replace('T','')[:-1]}00"
                    item_endtime = f"{item_endtime.replace('-','').replace(':','').replace('T','')[:-1]}00"
                #    start = item_starttime.split(' UTC')
                #    item_starttime = start[0].replace(' ', '').replace('-', '').replace(':', '')
                #    stop = item_endtime.split(' UTC')
                #    item_endtime = stop[0].replace(' ', '').replace('-', '').replace(':', '')
                
                if not item_country == '':
                    item_country = item_country.upper()
                if item_agerating == '-1':
                    item_agerating = ''

                # Map Genres
                if not items_genre == '':
                    items_genre = mapper.map_genres(','.join(items_genre), genre_format, gn_genres_json, gracenote_genres_warnings_tmp, "GLOBAL")

                ## Create XML Broadcast Information with provided Variables
                xml_structure.xml_broadcast(episode_format, channel_id, item_title, item_starttime, item_endtime,
                                            item_description, item_country, item_picture, item_subtitle, items_genre,
                                            item_date, item_season, item_episode, item_agerating, item_starrating, items_director,
                                            items_producer, items_actor, enable_rating_mapper, lang, item_long_description)

        except (KeyError, IndexError):
            log('{} {} {} {} {} {}'.format(provider,loc(32367),channel_name,loc(32368),contentID,loc(32369)))
    pDialog.close()

    ## Create Channel Warnings Textile
    channel_pull = '\nPlease Create an Pull Request for Missing Rytec Id´s for gn_channels.json on https://www.kodinerds.net/thread/64901\n'
    mapper.create_channel_warnings(gracenote_channels_warnings_tmp, gracenote_channels_warnings, provider, channel_pull)

    ## Create Genre Warnings Textfile
    genre_pull = '\nPlease Create an Pull Request for Missing EIT Genres for gn_genres.json on https://www.kodinerds.net/thread/64901\n'
    mapper.create_genre_warnings(gracenote_genres_warnings_tmp, gracenote_genres_warnings, provider, genre_pull)

    notify(addon_name, '{} {} {}'.format(loc(32370),provider,loc(32371)), icon=xbmcgui.NOTIFICATION_INFO)
    log('{} {} {}'.format(loc(32370),provider,loc(32371), xbmc.LOGINFO))
    xbmc.sleep(4000)

    if (os.path.isfile(gracenote_channels_warnings) or os.path.isfile(gracenote_genres_warnings)):
        notify(provider, '{}'.format(loc(32372)), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmc.sleep(3000)

    ## Delete old Tempfiles, not needed any more
    for file in os.listdir(provider_temppath): xbmcvfs.delete(os.path.join(provider_temppath, file))


def check_provider():
    ## Create Provider Temppath if not exist
    if not os.path.exists(provider_temppath):
        os.makedirs(provider_temppath)

    ## Create empty (Selected) Channel List if not exist
    if not os.path.isfile(gracenote_chlist_selected):
        with open((gracenote_chlist_selected), 'w', encoding='utf-8') as selected_list:
            selected_list.write(json.dumps({"channellist": []}))

        ## If no Channellist exist, ask to create one
        yn = OSD.yesno(provider, loc(32405))
        if yn:
            select_channels()
        else:
            xbmcvfs.delete(gracenote_chlist_selected)
            return False

    ## If a Selected list exist, check valid
    valid = check_selected_list()
    if valid is False:
        yn = OSD.yesno(provider, loc(32405))
        if yn:
            select_channels()
        else:
            xbmcvfs.delete(gracenote_chlist_selected)
            return False
    return True

def startup():
    if check_provider():
        get_channellist()
        return True
    else:
        return False

# Channel Selector
try:
    if sys.argv[1] == 'select_channels_gracenote':
        select_channels()
        xbmcaddon.Addon(id='service.takealug.epg-grabber').openSettings()
    if sys.argv[1] == 'select_rating_gracenote':
        select_rating()
        xbmcaddon.Addon(id='service.takealug.epg-grabber').openSettings()
except IndexError:
    pass