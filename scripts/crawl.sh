#!/usr/bin/env bash

while true; do
    python3 crawler.py run
    python3 crawler.py update-users
    python3 crawler.py run-contest --contest-id 1 --pages-count 15
    python3 crawler.py run-contest --contest-id 2 --pages-count 15
    python3 crawler.py run-contest --contest-id 3 --pages-count 15
    python3 crawler.py run-contest --contest-id 4 --pages-count 15
    sleep 60;
done