Version 4.2 is out and it changes one thing you have to act on: the configuration file moved from
`./config.yml` to `./config/app.yml`.

Old paths keep working until 5.0, with a warning on start-up. To move now:

    mkdir -p config && git mv config.yml config/app.yml

Everything else in this release is internal. The full list is in the changelog.
