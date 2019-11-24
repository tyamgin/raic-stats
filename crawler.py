#!/usr/bin/python3
# -*- coding: utf-8 -*-

import config

import time
import logging
import traceback
import json

import pymysql
import click
import requests
from retry import retry
from lxml import html

logging.basicConfig(level=logging.INFO)
log = logging.getLogger()

STANDINGS_XPATH_TR = '//div[@class="commonBottom"]/table/tbody/tr'
GAMES_XPATH_GAME = '//div[@class="commonBottom"]/table/tbody/tr'
GAME_XPATH_GAME = '//div[@class="row singleGame"]'

LABELS = ("place", "player", "games", "won_perc", "rating", "delta")

SLEEP_TIME_SEC = 180


from db import db


class SiteScrapper(object):
    def __init__(self):
        if config.SEASON == '2019':
            self.base_url = 'https://russianaicup.ru/'
        else:
            self.base_url = f'https://{config.SEASON}.russianaicup.ru/'

    @retry(delay=1, backoff=2, max_delay=64, tries=6)
    def make_request(self, url):
        page = requests.get(f'{self.base_url}{url}')
        if page.status_code not in [200, 404]:
            raise RuntimeError(page.status_code)
        return page

    def crawl_game_page(self, game_id):
        log.info("Crawling game page {}".format(game_id))

        page = self.make_request(f'game/view/{game_id}')
        if page.status_code == 404 or page.url.endswith('russianaicup.ru/'):  # shit. detect "404"
            log.info(f"Got 404 for game {game_id}")
            return None
        tree = html.fromstring(page.content)

        game_id = int(tree.xpath('//meta[@name="og:title"]')[0].get('content')[6:])
        game_div = tree.xpath(GAME_XPATH_GAME)[0]
        kind = game_div.xpath('.//div[@class="gameType"]')[0].text_content().strip()
        creator = game_div.xpath('.//div[@class="gameContest"]')[0].text_content().strip()
        contest_id = {
            'Sandbox': 1,
            'Round 1': 2,
            'Round 2': 3,
            'Finals': 4,
        }.get(creator, 0)
        token = ''

        game = {
            "game_id": game_id,
            "kind": kind,
            "creator": creator,
            "token": token,
            "contest_id": contest_id,
            "scores": [],
        }

        for div in game_div.xpath('.//div[contains(@class, "topUser")]'):
            name_version_pair = div.xpath('.//p[@class="userName"]')[0].text_content().strip().split()
            game['scores'].append({
                "player": name_version_pair[0],
                "version": int(name_version_pair[1]),
                "score": int(div.xpath('.//p[@class="points"]')[0].text_content().strip().split()[0]),
                "place": int(div.xpath('.//p[@class="place"]')[0].text_content().strip().split()[0]),
            })
        assert game['scores']
        return game

    def crawl_games_page(self, contest_num, page_num):
        games = []
        log.info("Crawling games page {} for contest {}".format(page_num, contest_num))

        page = self.make_request(f'contest/{contest_num}/games/page/{page_num}')
        tree = html.fromstring(page.content)
        try:
            for tr in tree.xpath(GAMES_XPATH_GAME):
                tds = tr.xpath("td")
                game_id_str = tds[0].text_content().strip()
                if game_id_str == 'No games':
                    log.debug("No games found in page {}".format(page_num))
                    return []

                game_id = int(game_id_str)

                if "Game is testing now" in tr.text_content():
                    log.debug("Skipping game {}, still testing".format(game_id))
                    continue

                kind = tds[1].text_content().strip()
                creator = tds[3].text_content().strip()
                players = tds[4].text_content().split()
                versions = tds[5].text_content().split()
                scores = tds[6].text_content().split()
                places = tds[7].text_content().split()
                deltas = tds[8].text_content().split()
                token = tds[9].xpath("div")[0].get("data-token")
                if not deltas:
                    deltas = [None] * 10
                    log.debug("Game {} is not ready yet".format(players))

                data = list(zip(players, versions, scores, places, deltas))

                game = {
                    "game_id": game_id,
                    "kind": kind,
                    "creator": creator,
                    "token": token,
                    "contest_id": contest_num,
                    "scores": [
                        {
                            "player": player,
                            "version": int(version),
                            "score": int(score),
                            "place": int(place),
                            "delta": int(delta) if delta is not None else None
                        } for player, version, score, place, delta in data
                    ]
                }

                games.append(game)
        except Exception:
            games = None
            log.error(traceback.format_exc())

        assert games
        return games

    def crawl_top(self, contest_id):
        log.info("Crawling standings")
        standings = []
        first_place = None
        page = 1
        while page < 100:
            try:
                page_standings = self.crawl_standings_page(contest_id, page)
                if page_standings[0]["place"] == first_place:
                    log.info("Ended crawling standings at page {}".format(page))
                    break
                first_place = page_standings[0]["place"]
                standings += page_standings
                page += 1
            except:
                log.error(traceback.format_exc())
                standings = None
                break
            time.sleep(0.3)
        return standings

    def crawl_standings_page(self, contest_id, page_num):
        players = []
        log.info("Crawling standings page {} for contest {}".format(page_num, contest_id))

        page = self.make_request(f'contest/{contest_id}/standings/page/{page_num}')
        tree = html.fromstring(page.content)
        for tr in tree.xpath(STANDINGS_XPATH_TR):
            try:
                tc = tr.text_content().split()
                if tc[3] == '/':
                     del tc[3:5]
                player = dict(zip(LABELS, tc))
                for k, v in list(player.items()):
                    if k != "player":
                        try:
                            if v == '-':
                                v = '0'
                            v = int(v) if "." not in v else float(v.replace("%", ""))
                        except Exception:
                            log.warning("Exception while parsing {}, fallback to 0".format(v))
                        player[k] = v
                player['avatar'] = ''
                for img in tr.xpath('.//img[contains(@class, "userImage")]'):
                    player['avatar'] = img.get('src')
                players.append(player)
            except Exception:
                log.error("Couldn't parse player: {}".format(
                    tr.text_content()))
                log.error("Couldn't parse player (splitted): {}".format(
                    tr.text_content().split()))
                log.error(traceback.format_exc())

        return players


@click.group()
def main():
    pass


def insert_games(games):
    try:
        cur = db().cursor()
        for game in games:
            cur.execute("SELECT * FROM games WHERE game_id = %s", game['game_id'])
            if cur.rowcount == 0:
                for line in game['scores']:
                    cur.execute(
                        "INSERT INTO games (game_id, kind, contest_id, timestamp, creator, token, player_name, player_version, score, place)"
                        "           VALUES (%s,      %s,   %s,         %s,        %s,      %s,    %s,          %s,             %s,    %s)",
                        (game['game_id'], game['kind'], game['contest_id'], 0, game['creator'], game['token'],
                         line['player'], line['version'], line['score'], line['place']))
            else:
                log.error(f"Trying to insert game_id={game['game_id']} duplicate")
        db().commit()
    except Exception:
        db().rollback()
        raise


@main.command()
@click.option('--contest-id', type=int, default=2)
def run_contest(contest_id):
    scrapper = SiteScrapper()

    for page in range(1, 10**5):
        games = scrapper.crawl_games_page(contest_id, page)
        if games is None:
            continue
        if len(games) == 0:
            break

        try:
            insert_games(games)
        except Exception:
            log.error(traceback.format_exc())
        time.sleep(1)


def get_setting(setting, default=None):
    with db().cursor() as cursor:
        cursor.execute("SELECT * FROM settings WHERE setting=%s", setting)
        for row in cursor.fetchall():
            return row['value']
        return default


def update_setting(setting, value):
    with db().cursor() as cursor:
        try:
            cursor.execute("SELECT * FROM settings WHERE setting = %s", setting)
            if cursor.rowcount == 0:
                cursor.execute("INSERT INTO settings (setting, value) VALUES (%s, %s)", (setting, value))
            else:
                cursor.execute("UPDATE settings SET value=%s WHERE setting=%s ", (value, setting))
            db().commit()
        except:
            db().rollback()
            raise


@main.command()
def run():
    scrapper = SiteScrapper()

    game_id = int(get_setting('last_id', 388810)) + 1

    while True:
        game = scrapper.crawl_game_page(game_id)
        if not game:  # 404
            # check for deleted game
            with db().cursor() as cursor:
                cursor.execute("SELECT MAX(game_id) AS max_game_id FROM games")
                max_game_id = cursor.fetchone()['max_game_id']
                log.info(f"Max game_id is {max_game_id}")
                if max_game_id <= game_id:
                    break

        if game:
            insert_games([game])
        update_setting('last_id', game_id)
        game_id += 1
        time.sleep(0.3)


@main.command()
@click.option('--contest-id', default='1')
def update_users(contest_id):
    scrapper = SiteScrapper()

    standings = scrapper.crawl_top(contest_id)
    if not standings:
        return

    vals = [[row['place'], row['player'], row['games'], row['won_perc'], row['rating'], row['avatar']]
            for row in standings]

    try:
        with db().cursor() as cursor:
            cursor.execute("DELETE FROM users")

            cursor.executemany("INSERT INTO users (place, name, games, won_perc, rating, avatar)"
                               "VALUES            (%s,    %s,   %s,    %s,       %s,     %s)",
                               vals)
            db().commit()
    except:
        db().rollback()
        log.error(traceback.format_exc())


@main.command()
def prepare_db():
    cur = db().cursor()
    log.info("Creating table games")
    cur.execute("""CREATE TABLE IF NOT EXISTS games (
        id int NOT NULL PRIMARY KEY auto_increment,
        game_id int NOT NULL,
        kind varchar(10),
        contest_id int NOT NULL,
        timestamp int unsigned NOT NULL,
        creator varchar(50) NOT NULL,
        token varchar(50),
        player_name varchar(50) NOT NULL,
        player_version int NOT NULL,
        team_idx int,
        score int,
        place int
    );""")

    for col in ('id', 'game_id', 'kind', 'contest_id', 'player_name'):
        log.info(f"Creating index games({col})")
        try:
            cur.execute(f"CREATE INDEX {col} ON games ({col});")
        except Exception:
            err_str = traceback.format_exc()
            if not 'Duplicate key name' in err_str:
                raise
            else:
                log.warning(f"Index games({col}) already exists")

    log.info("Creating table users")
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id int NOT NULL PRIMARY KEY auto_increment,
        place int NOT NULL,
        name varchar(50) NOT NULL,
        games int NOT NULL,
        won_perc int NOT NULL,
        rating int NOT NULL,
        avatar text NOT NULL
    );""")

    log.info("Creating table settings")
    cur.execute("""CREATE TABLE IF NOT EXISTS settings (
        id int NOT NULL PRIMARY KEY auto_increment,
        setting text NOT NULL,
        value text NOT NULL
    );""")





if __name__ == "__main__":
    main()
