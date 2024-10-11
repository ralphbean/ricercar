#!/usr/bin/env python

import copy

import click

import jql

RICE = [
    'Reach',
    'Impact',
    'Confidence',
    'Effort'
]


@click.group()
@click.option('--force', is_flag=True, help="Prompt and set values even if they are already set")
@click.pass_context
def cli(ctx, force):
    # ensure that ctx.obj exists and is a dict (in case `cli()` is called
    # by means other than the `if` block below)
    ctx.ensure_object(dict)
    ctx.obj['force'] = force

class NULL(Exception):
    pass

def float_or_null(x):
    if x is NULL:
        return x
    return float(x)


def confidence_processor(x):
    if x is NULL:
        return x
    x = x.strip("%")
    lookup = {
        "50": {"value": "50% (Low)", "id": "27779"},
        "75": {"value": "75% (Medium)", "id": "27778"},
        "100": {"value": "100% (High)", "id": "27777"},
    }
    return lookup[x]


processors = {
    "Reach": float_or_null,
    "Impact": float_or_null,
    "Confidence": confidence_processor,
    "Effort": float_or_null,
}


def custom_sort(key):
    # Put Confidence last, because you only want to specify confidence after
    # you've specified the others.
    order = ["Reach", "Impact", "Effort", "Confidence"]
    return order.index(key)


def process(issue, force, prompts, client, fieldmap):
    click.echo(f"{issue.permalink().ljust(46)} {issue.fields.summary}")
    updates = {}
    for field in sorted(prompts, key=custom_sort):
        value = getattr(issue.fields, fieldmap[field])
        if value is None or force:
            value = click.prompt(f" {field}({value})", value_proc=processors[field], default=NULL, show_default=False)
            if value is not NULL:
                click.echo(f"    Will update {field} on {issue.key} to {value}")
                updates[fieldmap[field]] = value
            else:
                click.echo(f"    Skipping {field}")
    if updates:
        click.echo(f"    Applying updates to {issue.key}: {updates}")
        issue.update(updates)

   
def process_rice_options(force, reach, impact, confidence, effort):
    prompts = set()
    rice_clauses = set()
    if reach:
        rice_clauses.add("Reach is EMPTY")
        prompts.add("Reach")

    if impact:
        rice_clauses.add("Impact is EMPTY")
        prompts.add("Impact")

    if confidence:
        rice_clauses.add("Confidence is EMPTY")
        prompts.add("Confidence")

    if effort:
        rice_clauses.add("Effort is EMPTY")
        prompts.add("Effort")

    if not reach and not impact and not confidence and not effort:
        rice_clauses.add("Reach is EMPTY")
        rice_clauses.add("Impact is EMPTY")
        rice_clauses.add("Confidence is EMPTY")
        rice_clauses.add("Effort is EMPTY")
        prompts = set(["Reach", "Impact", "Confidence", "Effort"])

    return prompts, rice_clauses


@cli.command()
@click.option('--query', required=True, help="JIRA query to burn through")
@click.option('--reach', is_flag=True, help="Focus only on Reach values")
@click.option('--impact', is_flag=True, help="Focus only on Impact values")
@click.option('--confidence', is_flag=True, help="Focus only on Confidence values")
@click.option('--effort', is_flag=True, help="Focus only on Effort values")
@click.option('--limit', type=int, default=10, help="Total number of issues to loop through")
@click.pass_context
def burndown(ctx, query, reach, impact, confidence, effort, limit):
    """ Iterate over features with missing RICE fields and set them. """
    force = ctx.obj['force']
    client = jql.get_jira()
    fieldmap = dict([(f['name'], f['id']) for f in client.fields()])

    prompts, clauses = process_rice_options(force, reach, impact, confidence, effort)
    rice_query = " OR ".join(list(clauses))
        
    full_query = f"({rice_query}) and {query}"
    issues = jql.search(client, full_query, limit=limit)
    for issue in issues:
        process(issue, force, prompts, client, fieldmap)
    click.echo("Done")


@cli.command('set')
@click.argument('key')
@click.pass_context
def set_jira(ctx, key):
    """ Set RICE values on an individual JIRA, by id. """
    force = ctx.obj['force']
    client = jql.get_jira()
    fieldmap = dict([(f['name'], f['id']) for f in client.fields()])
    issue = jql.get(client, key)
    process(issue, force, RICE, client, fieldmap)
    click.echo("Done")


if __name__ == '__main__':
    cli(obj={})
