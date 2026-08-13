# Fixtures with exactly one reader

Well-built messages whose correctness depends on having a single addressee — a direct message, a reply
to one person. Second person is right in all of them.

They are **not** in `well-built/`, because the harness hands every negative the same situation and does
not say where it is going. Measured as a broadcast, a direct message reads as addressing one member of
a group, and the `address` check is right to say so. Keeping them in the shared set would have taught
that check to accept a real defect.

Measure them with the destination named:

```
python3 measure/measure_check.py --check address --negatives 'measure/fixtures/one-reader/*.md' \
    --who "one colleague, in a direct message, who is already in this conversation"
```
