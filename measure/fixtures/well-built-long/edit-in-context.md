Judge an edit inside its document, and record only real expansions

An agent running the previous version reported that the checks judge the edit payload rather than the
resulting document. Both "no sentence stating what this list is for" complaints landed on a file whose first
paragraph is exactly that, because the edit only touched the middle, and a reference that resolved forty
lines up read as unresolved for the same reason. Confirmed by running it: an Edit was handed `new_string`
alone, while `previous` was already reading the whole file from disk for another purpose.

The checks now get the document as it will be after the call. The other half matters as much: a complaint
about a paragraph the edit never touched is worth saying and is not grounds for refusing the edit, so the
caller is told which sentences this call wrote and blocks only on those.

Expansion recording, added yesterday, was measured against 31,453 real documents and was mostly wrong. It
produced `PREVIEW]` with nineteen netlify URLs, `E.G.` with three sentence fragments, `CDM -> cdm/pull/653>`,
and three coincidental parentheticals that each read as a second meaning: "child model (CDM)", "Xerces
validation (XSD)", "recently released (RC)". A written-out form now has to be words rather than a link or a
path, between two and eight of them, and its initials have to match the acronym in order, skipping the words
an expansion skips. That took 59 recorded terms down to 10, all of them correct, and took the reported
ambiguities from 6 to none — which is the honest answer for this corpus: `LF` is never written out in it, so
there is nothing to disambiguate with.

A heredoc is a script and not a message. A docstring inside one is prose, so `cd somewhere` was offered as a
destination on the strength of a heredoc it happened to carry — this very session, on its own test suite. The
stated cost is that `cat > notes.md <<MD ... MD` writes a prose file and is no longer noticed.

BTW joins the everyday abbreviations and E2E, NPE, HMR and LTS the developer baseline, on the same argument
as FAQ and UK before them: every team that measures an audience would otherwise spend its judgement on the
same terms and reach the same answer.
