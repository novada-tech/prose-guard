# Negative fixtures

Ordinary, well-built messages. Every check has to **pass** these, or it is firing on prose rather than
on a defect.

They are hand-written rather than collected, which is a limitation worth knowing: they cannot show you
what your check does to the messages your team actually writes. Point `--negatives` at your own
outgoing messages when you have some, and treat these as the floor.

Keep them short, keep them varied, and keep them genuinely good. A negative fixture with a real defect
in it teaches a check to accept that defect.
