# Projects

*Jobs, tasks and what they have cost — Fuse Projects user guide 01*

## Before you start

### What Projects is for

Not everything a business does is a production run. Some work is a job: an installation, a
commissioning, a service call, a build on a customer's site. It has a start and an end,
people book time to it, and somebody wants to know at the end what it cost.

That is what Projects records.

### Where projects come from

**From Intacct.** Projects and their tasks are raised in Intacct and mirrored here, so
that the people doing the work see the same job list as the people costing it.

On a site set up that way, the New button on Projects is hidden and creating one here is
refused. A project invented in Fuse would be one Intacct has never heard of, and the time
booked to it would have nowhere to go.

Two switches in Intacct Settings control this:

| Switch | What it does |
|---|---|
| Projects from Intacct | Projects and tasks are mirrored, and creating them here is locked |
| Post project updates | Task status changes and timesheets are sent back to Intacct |

> **Screenshot 1 — Fuse Home with the Projects tile**
> *[to be inserted: Fuse Home, reference row, Projects tile]*

## The Projects page

Click **Projects** on Fuse Home.

| What you see | What it tells you |
|---|---|
| Project | The job, as Intacct knows it |
| Status | Open, Completed, or Cancelled |
| Tasks | The pieces of work that make it up |
| Cost | What has been booked against it so far |

Open a project to see its task list. A task is the unit people actually book against — one
job may have three tasks or thirty.

> **Screenshot 2 — A project with its tasks**
> *[to be inserted: Project form showing the task list]*

## Working a job

### Marking a task

1. Open the task.
2. Set the **Status** — Open, Working, Pending Review, Completed, or Cancelled.
3. Save.

Where **Post project updates** is on, the change is sent to Intacct as you save it. The
people costing the job see the same status as the people doing it, without anybody sending
a message.

### Booking time

1. Open the task, or go to Timesheet.
2. Add a row: the employee, the activity type, the hours, and the task.
3. Submit.

On submit the timesheet is posted to Intacct against the same project and task. That is
what makes the cost on the project real rather than an estimate.

> **Screenshot 3 — A timesheet against a task**
> *[to be inserted: Timesheet with one row against a project task]*

## On a phone or tablet

The **Site Work** screen is built for someone standing on a job rather than sitting at a
desk. It shows the tasks assigned to them, lets them change a status with one tap, and
lets them log time without opening a form.

Reach it from Shop floor screens on Fuse Home, or bookmark it directly.

> **Screenshot 4 — The Site Work screen on a phone**
> *[to be inserted: fuse-projects-floor page on a phone-width screen]*

## Common questions

### A project I expect is not here

It is not open in Intacct, or the sync has not run since it was raised. Check Intacct
first; then re-run the project sync from Intacct Settings.

### The New button is missing

The site is set up with Intacct as the source for projects. Raise it there and it appears
here on the next sync.

### Can I add a task to an existing project?

Yes, where the site allows it — a new task is created here and pushed to Intacct, so both
sides stay in step. A whole new project is not, for the reason above.

### The cost looks too low

Time booked but not submitted does not count. Check for draft timesheets. Cost from
materials and purchases comes from Intacct, so a job costed only on labour here is usually
a job whose purchases have not been posted there yet.
