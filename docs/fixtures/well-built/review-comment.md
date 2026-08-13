This drops the retry on a timeout, which I think is the one case we need it: the upstream service
returns 504 under load roughly once a day and the old code recovered from that silently.

Worth checking against the incident from last month before merging — if I have the sequence wrong, say
so and I will withdraw this.

The rest reads well, and moving the parsing out of the handler makes the error path much easier to
follow.
