#!/usr/bin/env python3
import logging

import requests
import os
import os.path
import sys
import json
import argparse
import traceback

global clientid
global args
global stats


def main():
    parser = argparse.ArgumentParser(prog='main.py')
    parser.add_argument('--subreddits', '-s', action='store', dest='subs', default='desertporn,earthporn,ruralporn,rustyrails', help='comma-delimited list of subreddits to scrape')
    parser.add_argument('-d', action='store', dest='directory', default='images/', help='directory to download images into')
    parser.add_argument('-c', action='store', dest='config_file', default='config.json', help='config file')
    parser.add_argument('--sort', dest='sort', choices=['hot', 'new', 'top-all-time', 'top-month', 'top-week', 'top-day'], default='top-all-time', help='use new posts instead of top posts')
    parser.add_argument('-p', action='store', dest='pages', type=int, default=10, help='number of pages per subreddit to scrape (default 10)')
    parser.add_argument('--dry-run', action='store_true', dest='dry_run', help='list images to download but don\'t download them')
    parser.add_argument('-v', action='store_true', dest='verbose', help='show more output')

    global args
    args = parser.parse_args(sys.argv[1:])

    global stats
    stats = {
        'pages_crawled': 0,
        'images_downloaded': 0,
        'images_skipped': 0
    }

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(message)s')
        logging.debug('enabled verbose logging')
    else:
        logging.basicConfig(level=logging.INFO, format='%(message)s')

    if not os.path.exists(args.directory):
        os.mkdir(args.directory)
        logging.info(f'created nonexistent directory {args.directory}')

    with open(args.config_file) as keyfile:
        data = json.loads(keyfile.read())
        if 'clientid' not in data:
            logging.warning('clientid field isn\'t in json')
        else:
            global clientid
            clientid = data['clientid']

    if args.pages < 1:
        logging.error('must scrape at least one page')
        exit(1)

    for sub in args.subs.split(','):
        url_params = {}

        if args.sort == 'hot':
            suffix = 'hot/'
        elif args.sort == 'new':
            suffix = 'new/'
        elif args.sort == 'top-month':
            suffix = 'top/'
            url_params = {'sort': 'top', 't': 'month'}
        elif args.sort == 'top-week':
            suffix = 'top/'
            url_params = {'sort': 'top', 't': 'week'}
        elif args.sort == 'top-day':
            suffix = 'top/'
            url_params = {'sort': 'top', 't': 'day'}
        else:
            suffix = 'top/'
            url_params = {'sort': 'top', 't': 'all'}

        link = f'https://www.reddit.com/r/{sub}/{suffix}.json' + generate_get_params(url_params)

        for i in range(0, args.pages):
            logging.info(f'crawling {link}')
            after = crawl_page(link, sub)
            if after is None:
                break
            url_params['count'] = 25
            url_params['after'] = 't3_' + after
            link = f'https://www.reddit.com/r/{sub}/{suffix}.json' + generate_get_params(url_params)

    logging.info('')
    logging.info(f'pages crawled: {stats["pages_crawled"]}')
    logging.info(f'images downloaded: {stats["images_downloaded"]}')
    logging.info(f'images skipped : {stats["images_skipped"]} (because they\'re already downloaded)')


def crawl_page(link, sub):

    page = get_and_decode_json(link)

    posts = page['data']['children']

    posts = [post for post in posts if sub not in post['data']['domain']]

    image_links = {}
    after = None

    for post in posts:
        url = post['data']['url']

        if 'preview' not in post['data']:
            # No size, no save
            verbose(0, f'no size found, ignoring {url}')
            continue

        # this is why we can't have nice things
        width = str(post['data']['preview']['images'][0]['source']['width'])
        height = str(post['data']['preview']['images'][0]['source']['height'])
        after = post['data']['id']

        if not image_is_right_size(width, height):
            continue

        if url.endswith('.jpg') or url.endswith('.png'):
            verbose(1, f'found simple image {url}')

            image_links[post['data']['id']] = url

        elif 'imgur' in url and '/a/' in url:
            verbose(1, f'found imgur album {url}')

            album_hash = url.replace('http://imgur.com/a/', '').replace('https://imgur.com/a/', '')[:5]

            try:
                imgur = get_and_decode_json('https://api.imgur.com/3/album/' + album_hash)
                # TODO check for problem
                data = imgur['data']

                if 'error' in data:
                    logging.error(data['error'])
                    continue

                for image in data['images']:
                    verbose(2, f'found image {image["id"]}')
                    image_links[image['id']] = image['link']
            except Exception:
                traceback.print_exc()
        elif 'imgur' in url:
            verbose(1, f'found imgur image {url}')

            album_hash = url.replace('http://imgur.com/', '').replace('https://imgur.com/', '')\
                .replace('http://i.imgur.com/', '').replace('https://i.imgur.com/', '')

            image_links[album_hash] = url + ".jpg"
        else:
            verbose(0, f'skipping unhandled case {url}')

    # Fetch the images
    logging.info('')
    if args.dry_run:
        logging.info('dry run, skipping downloads')
    else:
        for id, link in image_links.items():
            filename = 'images/' + id + '.jpg'
            if not os.path.isfile(filename):
                verbose(1, f'downloading {link}...')
                try:
                    timeout(download_image, (link, filename), timeout_duration=10)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logging.error(e)
            else:
                verbose(1, f'skipping {link}, already downloaded...')
                stats['images_skipped'] += 1

    return after


def get_and_decode_json(url):
    global clientid
    headers = {
        'User-Agent': 'this is my fancy user agent',
        'Authorization': f'Client-ID {clientid}'
    }

    request = requests.get(url, headers=headers)
    return json.loads(request.text)


def image_is_right_size(width, height):
    # if it's big and landscape that's good enough
    return int(width) >= 1920 and int(height) >= 1080 and int(width) > int(height)


def download_image(url, dest):
    for i in range(0, 10):
        d = requests.get(url, params=None, allow_redirects=False)
        if d.status_code == 200:
            f = open(dest, 'wb')
            f.write(d.content)
            f.close()
            stats['images_downloaded'] += 1
            return
        elif d.status_code in [301, 302]:
            url = d.headers['location']
        else:
            logging.warning(f'got unexpected HTTP code {d.status_code}')

    logging.warning('maximum retries exceeded, stopping')


def generate_get_params(d):
    return '?' + str.join('&', [str(param) + '=' + str(d[param]) for param in d])


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


def verbose(indentation, message):
    if args.verbose:
        logging.debug(('  ' * indentation) + message)


if __name__ == '__main__':
    main()

