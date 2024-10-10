#!/usr/bin/env python

import copy

import click

import jql

RICE = [
    'Reach',
    'Impact',
    # 'Confidence',
    'Effort'
]


@click.group()
def cli():
    pass

class NULL(Exception):
    pass

def int_or_null(x):
    if x is NULL:
        return x
    return int(x)


def confidence_processor(x):
    return int_or_null(x)


processors = {
    "Reach": int_or_null,
    "Impact": int_or_null,
    "Confidence": confidence_processor,
    "Effort": int_or_null,
}

def process(issue, force, rice, client, fieldmap):
    click.echo(f"{issue.permalink().ljust(46)} {issue.fields.summary}")
    for field in rice:
        value = getattr(issue.fields, fieldmap[field])
        if value is None or force:
            value = click.prompt(f" {field}({value})", value_proc=processors[field], default=NULL, show_default=False)
            if value is not NULL:
                click.echo(f"    Updating {field} on {issue.key} to {value}")
                issue.update({fieldmap[field]: value})
            else:
                click.echo(f"    Skipping {field}")

   
def process_rice_options(force, reach, impact, confidence, effort):
    prompts = copy.copy(RICE)
    rice_clauses = []
    if reach:
        rice_clauses.append("Reach is EMPTY")
    if reach or force:
        prompts.append("Reach")

    if impact:
        rice_clauses.append("Impact is EMPTY")
    if impact or force:
        prompts.append("Impact")

    if confidence:
        rice_clauses.append("Confidence is EMPTY")
    if confidence or force:
        prompts.append("Confidence")

    if effort:
        rice_clauses.append("Effort is EMPTY")
    if confidence or force:
        prompts.append("Effort")

    return prompts, rice_clauses


@cli.command()
@click.option('--query', required=True)
@click.option('--force', is_flag=True)
@click.option('--reach/--no-reach', default=True)
@click.option('--impact/--no-impact', default=True)
@click.option('--confidence/--no-confidence', default=True)
@click.option('--effort/--no-effort', default=True)
def burndown(query, force, reach, impact, confidence, effort):
    """ Iterate over features that do not have their RICE fields set, and set them. """
    client = jql.get_jira()
    fieldmap = dict([(f['name'], f['id']) for f in client.fields()])

    prompts, clauses = process_rice_options(force, reach, impact, confidence, effort)
    rice_query = " OR ".join(clauses)
        
    full_query = f"({rice_query}) and {query}"
    issues = jql.search(client, full_query)
    for issue in issues:
        process(issue, force, prompts, client, fieldmap)
    click.echo("Done")


@cli.command()
@click.argument('key')
@click.option('--force', is_flag=True)
def set(key, force):
    client = jql.get_jira()
    fieldmap = dict([(f['name'], f['id']) for f in client.fields()])
    issue = jql.get(client, key)
    process(issue, force, RICE, client, fieldmap)
    click.echo("Done")


if __name__ == '__main__':
    cli()
