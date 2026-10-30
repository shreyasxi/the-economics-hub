# RBI State of the Economy fixtures

The HTML fixtures are saved RBI article tables. `2026-09.pdf` is the unmodified
September 2026 article, downloaded automatically from the RBI Bulletin contents
on 29 September 2026 (2,894,117 bytes).

Source: https://rbidocs.rbi.org.in/rdocs/Bulletin/PDFs/1ARTICLE25092026551C90FB61784218909A840A2A4F1E39.PDF

The PDF fixture covers line-by-line paragraph exports, two-column reading order,
a conclusion spanning pages, and numbered transmission columns with merged
headers. On printed page 60, the July easing-cycle figures are: fresh loans
-81 bps, interest-rate effect -75 bps, outstanding loans -90 bps. The latter is
the final printed column. Preserve the original source rather than editing the
fixture to make a parser test pass.

`2026-10.pdf` is the unmodified October 2026 article supplied as
`docs/latest_SOE.pdf`. Source:
https://rbidocs.rbi.org.in/rdocs/Bulletin/PDFs/01ARTICLE23102026026657A9D5FE49CA9595B3F593D46E4C.PDF

Printed pages 149-150 cover tightly spaced headers and a shared fresh-WALR
heading. August cumulative figures: fresh deposits -95, fresh loans -72,
fixed-weight fresh loans -76, outstanding loans -91 bps. August memo: fresh
loans +9 versus fixed-weight -1 bps. The conclusion also contains justified
words exported as separate PDF lines; none may be dropped from the briefing.
