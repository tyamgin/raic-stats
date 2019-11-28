#!/usr/bin/python3
# -*- coding: utf-8 -*-

from db import db, db_init
from site_scrapper import SiteScrapper

import time
import logging
import traceback
import json

import pymysql
import click

logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')
log = logging.getLogger()


@click.group()
def main():
    pass


def insert_game(game):
    try:
        with db().cursor() as cursor:
            cursor.execute("SELECT * FROM games WHERE game_id = %s", game['game_id'])
            if cursor.rowcount == 0:
                for line in game['scores']:
                    cursor.execute(
                        "INSERT INTO games (game_id, kind, contest_id, timestamp, creator, token, player_name, player_version, score, place)"
                        "VALUES            (%s,      %s,   %s,         %s,        %s,      %s,    %s,          %s,             %s,    %s)",
                        (game['game_id'], game['kind'], game['contest_id'], 0, game['creator'], game['token'],
                         line['player'], line['version'], line['score'], line['place']))
            else:
                log.debug(f"Trying to insert game_id={game['game_id']} duplicate")
            db().commit()
    except Exception:
        db().rollback()
        raise


@main.command()
@click.option('--contest-id', type=int, default=1)
@click.option('--pages-count', type=int, default=10000)
def run_contest(contest_id, pages_count):
    scrapper = SiteScrapper()
    max_id = 0

    for page in range(1, pages_count + 1):
        games = scrapper.crawl_games_page(contest_id, page)
        if games is None:
            continue
        if len(games) == 0:
            break

        try:
            for game in games:
                if game["status"] == "tested":
                    insert_game(game)
                max_id = max(max_id, game["game_id"])

        except Exception:
            log.error(traceback.format_exc())
        time.sleep(1)

    update_setting("max_id", max(max_id, int(get_setting("max_id", 0))))


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
@click.option('--only-game-id', type=int, default=0)
def run(only_game_id):
    scrapper = SiteScrapper()

    if only_game_id:
        game_id = only_game_id
    else:
        game_id = int(get_setting('last_id', 0)) + 1

    while True:
        game = scrapper.crawl_game_page(game_id)
        if not game:  # 404
            # check for deleted game
            max_game_id = int(get_setting("max_id", 0))
            log.info(f"Max game_id is {max_game_id}")
            if max_game_id <= game_id:
                log.info(f"Game {game_id} is probably deleted, skip it")
                break
        if game and game["status"] == "testing":
            log.info("Last status 'testing', break")
            break

        if game and game["status"] == "tested":
            insert_game(game)
        if only_game_id:
            break

        update_setting('last_id', game_id)
        game_id += 1
        time.sleep(0.3)


@main.command()
@click.option('--contest-id', default='1')
def update_users(contest_id):
    log.info("Starting update_users")
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
    log.info("update_users finished")

@main.command()
def prepare_db():
    with db().cursor() as cursor:
        log.info("Creating table games")
        cursor.execute("""CREATE TABLE IF NOT EXISTS games (
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

        for col in ('id', 'game_id', 'kind', 'contest_id', 'player_name', 'player_version'):
            log.info(f"Creating index games({col})")
            try:
                cursor.execute(f"CREATE INDEX {col} ON games ({col});")
            except Exception:
                err_str = traceback.format_exc()
                if not 'Duplicate key name' in err_str:
                    raise
                else:
                    log.warning(f"Index games({col}) already exists")

        log.info("Creating table users")
        cursor.execute("""CREATE TABLE IF NOT EXISTS users (
            id int NOT NULL PRIMARY KEY auto_increment,
            place int NOT NULL,
            name varchar(50) NOT NULL,
            games int NOT NULL,
            won_perc int NOT NULL,
            rating int NOT NULL,
            avatar text NOT NULL
        );""")

        log.info("Creating table settings")
        cursor.execute("""CREATE TABLE IF NOT EXISTS settings (
            id int NOT NULL PRIMARY KEY auto_increment,
            setting text NOT NULL,
            value text NOT NULL
        );""")


if __name__ == "__main__":
    db_init()
    main()
