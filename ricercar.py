#!/usr/bin/env python
"""🍙 A tool to help manage RICE values in JIRA 🍙 """

import concurrent.futures
import copy
import difflib

import click

import jql

RICE = ["Reach", "Impact", "Confidence", "Effort", "Parent Link"]


@click.group(help=__doc__)
@click.option(
    "--force", is_flag=True, help="Prompt and set values even if they are already set"
)
@click.pass_context
def cli(ctx, force):
    # ensure that ctx.obj exists and is a dict (in case `cli()` is called
    # by means other than the `if` block below)
    ctx.ensure_object(dict)
    ctx.obj["force"] = force


class NULL(Exception):
    pass


def float_or_null(x):
    if x is NULL:
        return x
    error = f"{x} must be a number greater than 0 and less than or equal to 5"
    try:
        value = float(x)
    except ValueError:
        raise click.UsageError(error)
    if value <= 0 or value > 5:
        raise click.UsageError(error)
    return value


def jira_outcome_processor(x):
    if x is NULL:
        return x
    lookup = {
        "1": "KONFLUX-6116",
        "2": "KONFLUX-6117",
        "3": "KONFLUX-6118",
    }
    try:
        return lookup[x]
    except KeyError:
        raise click.UsageError(f"{x} must be one of {lookup.keys()}")


def confidence_processor(x):
    if x is NULL:
        return x
    x = x.strip("%")
    lookup = {
        "50": {"value": "50% (Low)", "id": "27779"},
        "75": {"value": "75% (Medium)", "id": "27778"},
        "100": {"value": "100% (High)", "id": "27777"},
    }
    try:
        return lookup[x]
    except KeyError:
        raise click.UsageError(f"{x} must be one of {lookup.keys()}")


processors = {
    "Reach": float_or_null,
    "Impact": float_or_null,
    "Confidence": confidence_processor,
    "Effort": float_or_null,
    "Parent Link": jira_outcome_processor,
}


def custom_sort(key):
    # Put Confidence last, because you only want to specify confidence after
    # you've specified the others.
    order = ["Parent Link", "Reach", "Impact", "Effort", "Confidence"]
    return order.index(key)


def format_field(key):
    emojis = {
        "Parent Link": "⬆️ ",
        "Reach": "🖐️ ",
        "Impact": "👊",
        "Effort": "🥵",
        "Confidence": "😎",
    }
    return f"{emojis.get(key, '')} {key}".strip()


def empty(field, value):
    if field == 'Parent Link':
        # Hardcoded :( It would be better to check the statusCategory of the value but that's an extra call to JIRA.
        return value is None or value not in ["KONFLUX-6116", "KONFLUX-6117", "KONFLUX-6118"]
    else:
        return value is None


def format_issue(issue):
    return f"{issue.permalink().ljust(46)} {issue.fields.summary}"


def process(executor, issue, force, prompts, client, fieldmap):
    separator = "─" * 80
    click.echo(f"{separator}\n{format_issue(issue)}")
    updates = {}
    for field in sorted(prompts, key=custom_sort):
        value = getattr(issue.fields, fieldmap[field])
        if empty(field, value) or force:
            value = click.prompt(
                f" {format_field(field)}({value})",
                value_proc=processors[field],
                default=NULL,
                show_default=False,
            )
            if value is not NULL:
                click.echo(f"      ✅ Will update {field} on {issue.key} to {value}")
                updates[fieldmap[field]] = value
            else:
                click.echo(f"      ⚪ Skipping {field}")
    if updates:
        click.echo(f" 🌀 Applying updates to {issue.key} in the background: {updates}")
        executor.submit(issue.update, updates)


def process_rice_options(force, reach, impact, confidence, effort, outcome):
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

    if outcome:
        rice_clauses.add("('Parent Link' is EMPTY or issueFunction in portfolioChildrenOf('statusCategory = Done and type=Outcome'))")
        prompts.add("Parent Link")

    if not reach and not impact and not confidence and not effort and not outcome:
        rice_clauses.add("Reach is EMPTY")
        rice_clauses.add("Impact is EMPTY")
        rice_clauses.add("Confidence is EMPTY")
        rice_clauses.add("Effort is EMPTY")
        #rice_clauses.add("('Parent Link' is EMPTY or issueFunction in portfolioChildrenOf('statusCategory = Done and type=Outcome'))")
        prompts = set(["Reach", "Impact", "Confidence", "Effort"])  # , "Parent Link"])

    return prompts, rice_clauses


@cli.command()
@click.option("--query", required=True, help="JIRA query to burn through")
@click.option("--ignore", help="Comman-separated list of jiras to ignore")
@click.option("--reach", is_flag=True, help="Focus only on Reach values")
@click.option("--impact", is_flag=True, help="Focus only on Impact values")
@click.option("--confidence", is_flag=True, help="Focus only on Confidence values")
@click.option("--effort", is_flag=True, help="Focus only on Effort values")
@click.option("--outcome", is_flag=True, help="Focus only on Parent Link")
@click.option("--limit", type=int, default=10, help="Total number of issues")
@click.pass_context
def workflow(ctx, query, ignore, reach, impact, confidence, effort, outcome, limit):
    """Iterate over features with missing RICE fields and set them."""
    force = ctx.obj["force"]
    client = jql.get_jira()
    fieldmap = dict([(f["name"], f["id"]) for f in client.fields()])

    if ignore:
        exclusions = f"key not in ({ignore})"
        query = f"{exclusions} and {query}"

    prompts, clauses = process_rice_options(force, reach, impact, confidence, effort, outcome)
    rice_query = " OR ".join(list(clauses))

    full_query = f"({rice_query}) and {query}"

    issues = jql.search(client, full_query, limit=limit)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        for i, issue in enumerate(issues):
            click.echo(f"Issue {i} of {len(issues)}")
            process(executor, issue, force, prompts, client, fieldmap)
    click.echo("Done")


@cli.command("set")
@click.argument("key")
@click.pass_context
def set_jira(ctx, key):
    """Set RICE values on an individual JIRA, by id."""
    force = ctx.obj["force"]
    client = jql.get_jira()
    fieldmap = dict([(f["name"], f["id"]) for f in client.fields()])
    issue = jql.get(client, key)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        process(executor, issue, force, RICE, client, fieldmap)
    click.echo("Done")


@cli.command("list")
@click.option("--query", required=True, help="JIRA query to list")
@click.option("--ignore", help="Comman-separated list of jiras to ignore")
@click.option("--reach", is_flag=True, help="List only issues without Reach values")
@click.option("--impact", is_flag=True, help="List only issues without Impact values")
@click.option(
    "--confidence", is_flag=True, help="List only issues without Confidence values"
)
@click.option("--effort", is_flag=True, help="List only issues without Effort values")
@click.option("--outcome", is_flag=True, help="Focus only on Parent Link")
@click.option("--limit", type=int, default=10, help="Total number of issues")
def list_jira(query, ignore, reach, impact, confidence, effort, outcome, limit):
    """List features with missing RICE fields."""
    client = jql.get_jira()

    if ignore:
        exclusions = f"key not in ({ignore})"
        query = f"{exclusions} and {query}"

    prompts, clauses = process_rice_options(False, reach, impact, confidence, effort, outcome)
    rice_query = " OR ".join(list(clauses))

    full_query = f"({rice_query}) and {query}"
    issues = jql.search(client, full_query, limit=limit)
    for issue in issues:
        click.echo(format_issue(issue))


@cli.command("diff")
@click.option("--query", required=True, help="JIRA query to compare order")
@click.option("--ignore", help="Comman-separated list of jiras to ignore")
@click.option("--limit", type=int, default=10, help="Total number of issues")
def diff(query, ignore, limit):
    """Generate a diff of a query sorted by Rank vs RICE."""
    client = jql.get_jira()
    fieldmap = dict([(f["name"], f["id"]) for f in client.fields()])

    if ignore:
        exclusions = f"key not in ({ignore})"
        query = f"{exclusions} and {query}"

    if "ORDER BY" in query.upper():
        raise click.BadOptionUsage("query", "Query may not contain 'ORDER BY'")

    by_rank = "ORDER BY Rank"
    by_rice = "ORDER BY 'RICE Score' DESC"
    src = [
        f"{format_issue(i)}\n"
        for i in jql.search(client, f"{query} {by_rank}", limit=limit)
    ]
    dst = [
        f"{format_issue(i)}\n"
        for i in jql.search(
            client, f"{query} and 'RICE Score' is not EMPTY {by_rice}", limit=limit
        )
    ]

    click.echo("SRC")
    for line in src:
        click.echo(line.strip("\n"))
    click.echo("DST")
    for line in dst:
        click.echo(line.strip("\n"))

    for line in difflib.unified_diff(src, dst, fromfile=by_rank, tofile=by_rice):
        click.echo(line.strip("\n"))


if __name__ == "__main__":
    cli(obj={})
