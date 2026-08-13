Shells no longer ask you to log in every morning. If you have a terminal open from before today,
restart it once and it stops.

The cause was one line that wrote a short-lived token into the environment on every shell start. Local
tools ignored that token, but our infrastructure tool preferred it over the long-lived credential, and
it expired after an hour — so any plan run in an older shell failed with an authentication error that
looked like a permissions problem.

The line is gone. Continuous integration sets the variable itself where it is genuinely needed, so
nothing changes there.
