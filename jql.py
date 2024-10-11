#!/usr/bin/env python3

import dogpile.cache
import jira.client

import sys
import os

JIRA_URL = "https://issues.redhat.com"

cache = dogpile.cache.make_region().configure(
    "dogpile.cache.memory",
    expiration_time=300,
)


def get_auth():
    token = os.environ.get("JIRA_TOKEN")
    if not token:
        raise KeyError("JIRA_TOKEN must be defined to access jira.")
    return token


def get_jira():
    """Returns a JIRA client object."""
    token = get_auth()
    jira_config = dict(options=dict(server=JIRA_URL), token_auth=token)
    return jira.client.JIRA(**jira_config)


def get(client, key):
    print(f"[JQL] key={key}", file=sys.stderr)
    return client.issue(key)


def search(client, jql, limit):
    print(f"[JQL] {jql}", file=sys.stderr)
    return client.search_issues(jql, maxResults=limit)
