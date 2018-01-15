#! /usr/bin/env python3

import requests
import json
import urllib.request
import os
import os.path
import sys
import urllib
import json
import argparse
import traceback

global clientid
global args
global stats

def main():
    parser = argparse.ArgumentParser(prog='main.py')
    parser.add_argument('-d', action='store', dest='directory', default='images/', help='directory to download images into')
    parser.add_argument('-c', action='store', dest='config_file', default='config.json', help='config file')
    parser.add_argument('--top', '-t', action='store_true', dest='top', help='use top posts instead of new posts')
    parser.add_argument('-p', action='store', dest='pages', type=int, default=10, help='number of pages per subreddit to scrape')
    parser.add_argument('-v', action='store_true', dest='verbose', help='show more output')

    global args
    args = parser.parse_args(sys.argv[1:])

    global stats
    stats = {
        'pages_crawled': 0,
        'images_downloaded': 0,
        'images_skipped': 0
    }

    if not os.path.exists(args.directory):
        os.mkdir(args.directory)

    keyfile = open('config.json')
    data = json.loads(keyfile.read())
    if 'clientid' not in data:
        print('warning: clientid field isn\'t in json')
    else:
        global clientid
        clientid = data['clientid']

    if 'subreddits' not in data:
        print('error: subreddits list missing from config')
        exit(1)

    if args.pages < 1:
        print('error: must scrape at least one page')
        exit(1)

    if args.top:
        print('using top posts')
    else:
        print('using new posts')

    for sub in data['subreddits']:
        if args.top:
            top = 'top/'
            url_params = {'sort': 'top', 't': 'all'}
        else:
            top = ''
            url_params = {}

        link = 'https://www.reddit.com/r/' + sub + '/' + top + '.json' + get_params(url_params)

        after = None

        for i in range(0, args.pages):
            print('crawling link: ' + link)
            after = crawl_page(link, sub)
            if after == None:
                break
            url_params['count'] = 25
            url_params['after'] = 't3_' + after
            link = 'https://www.reddit.com/r/' + sub + '/' + top + '.json' + get_params(url_params)

    print()
    print('pages crawled: %d' % stats['pages_crawled'])
    print('images downloaded: %d' % stats['images_downloaded'])
    print('images skipped : %d (because they\'re already downloaded)' % stats['images_skipped'])

def crawl_page(link, sub):

    page = get_and_decode_json(link)

    #print(link)

    posts = page['data']['children']

    posts = [post for post in posts if not sub in post['data']['domain']]

    image_links = {}
    after = None

    for post in posts:
        #print(post['data']['url'])
        if 'preview' not in post['data']:
            # No size, no save
            verbose("no size found, ignoring link " + url)
            continue

        # this is why we can't have nice things
        width = str(post['data']['preview']['images'][0]['source']['width'])
        height = str(post['data']['preview']['images'][0]['source']['height'])
        url = post['data']['url']
        #print(url)
        after = post['data']['id']

        if not image_is_right_size(width, height):
            continue

        verbose('checking link ' + url)

        if url.endswith('.jpg') or url.endswith('.png'):
            verbose('  simple image')

            image_links[post['data']['id']] = url

        elif 'imgur' in url and '/a/' in url:
            verbose('  imgur album')

            album_hash = url.replace('http://imgur.com/a/', '').replace('https://imgur.com/a/', '')[:5]

            try:
                imgur = get_and_decode_json('https://api.imgur.com/3/album/' + album_hash)
                #TODO check for problem
                data = imgur['data']

                if 'error' in data:
                    print('error: ' + data['error'])
                    continue

                for image in data['images']:
                    verbose('    found image ' + image['id'])
                    image_links[image['id']] = image['link']
            except Exception as e:
                traceback.print_exc()
        elif 'imgur' in url:
            verbose('  imgur image')

            album_hash = url.replace('http://imgur.com/', '').replace('https://imgur.com/', '')\
                .replace('http://i.imgur.com/', '').replace('https://i.imgur.com/', '')

            image_links[album_hash] = url + ".jpg"
        else:
            verbose("skipping unhandled case " + url)

    # Fetch the images
    print()
    for id, link in image_links.items():
        filename = 'images/' + id + '.jpg'
        if not os.path.isfile(filename):
            verbose('\tdownloading ' + link + '...')
            try:
                timeout(download_image, (link, filename), timeout_duration=10)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(e)
        else:
            verbose('\tskipping ' + link + ', already downloaded...')
            stats['images_skipped'] += 1

    return after

def get_and_decode_json(url):
    global clientid
    headers = {}
    headers['User-Agent'] = 'this is my fancy user agent'
    headers['Authorization'] = 'Client-ID ' + clientid
    request = requests.get(url, headers=headers)
    return json.loads(request.text)

def image_is_right_size(width, height):
    # if it's big and landscape that's good enough
    return int(width) >= 1920 and int(height) >= 1080 \
        and int(width) > int(height)

def download_image(url, dest):
    for i in range(0, 10):
        d = requests.get(url, params = None, allow_redirects = False)
        if d.status_code == 200:
            f = open(dest, 'wb')
            f.write(d.content)
            f.close()
            stats['images_downloaded'] += 1
            return
        elif d.status_code in [301, 302]:
            url = d.headers['location']
        else:
            print("got unexpected HTTP code " + str(d.status_code))

    print('maximum retries exceeded, stopping')

def get_params(d):
    string = ''
    i = 0
    for param in d:
        start = '?' if i == 0 else '&'
        string += start + str(param) + '=' + str(d[param])
        i += 1

    return string

def timeout(func, args=(), kwargs={}, timeout_duration=1, default=None):
    import signal

    class TimeoutError(Exception):
        pass

    def handler(signum, frame):
        raise TimeoutError()

    # set the timeout handler
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(timeout_duration)
    try:
        result = func(*args, **kwargs)
    except TimeoutError as exc:
        result = default
    finally:
        signal.alarm(0)

    return result

def verbose(message):
    if args.verbose:
        print(message)

if __name__ == '__main__':
    main()

