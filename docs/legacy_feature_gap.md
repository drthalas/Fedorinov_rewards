# Legacy Feature Gap

Stage 3 changes the target from a read-only viewer toward a full functional legacy mirror on the safe development data root. Write features must remain blocked until a fresh backup exists and `WRITE_MODE=true` is explicitly enabled.

## Persons

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Add person | Form1, Form2 | Implemented in web dev write mode | Creates `person` row and media folder expectations | Stage 3B | yes | yes |
| Edit person | Form2 | Implemented in web dev write mode; form labels and short biography added in Stage 3I | Changes personal fields, links, comments, biography, rank, dates | Stage 3B plus Stage 3I | yes | yes |
| Delete person | Form1, Form2 | Implemented in web dev write mode; blocks delete while rewards exist | May orphan rewards/media if parity is expanded later | Stage 3B | yes | yes |
| Person photos | Form2, Form4 | Upload/replace, clipboard paste, clear/unlink, viewer/slideshow, and zoom/pan lightbox implemented in web dev write mode | Physical file deletion still deferred; Clipboard API needs Windows browser QA | Stage 3F plus Iteration 4 and later photo deletion stage | yes | yes |
| Short biography | Form2 / owner request | Implemented as `person.biography` with guarded idempotent migration and display in person/legacy cards | Adds schema column and personal text field | Stage 3I | yes for migration/write | yes for migration/write |

## Legacy Desktop Layout

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Main desktop shell | Form1 | Implemented as `/legacy` separate route | Layout parity only; no direct writes | Stage 3E | no | no |
| Rewards tab layout | Form1 | Implemented as `/legacy?tab=rewards` using existing guarded CRUD links; main list filters, totals, safe links, and double-click card open added in Iteration 1 | Delete controls must remain POST-only and write-mode gated; dependent guide selects still need UX polish | Stage 3E plus Iteration 1 | only for writes | only for writes |
| Search tab layout | Form1 | Reworked in Stage 3G with category, condition, value, grouped result tables, counts, and reset; Iteration 2 adds empty-category search and disables browser history suggestions | Database-backed live suggestions and auto-submit JS still deferred | Stage 3G plus Iteration 2 | no | no |
| Marks tab layout | Form1 | Implemented as `/legacy?tab=marks` using existing guarded CRUD links | Delete controls must remain POST-only and write-mode gated | Stage 3E | only for writes | only for writes |
| Summary tab matrix | Form1 | Implemented as `/legacy?tab=summary` default `Шахматка по кавалерам`: persons as rows, reward names as columns, photo/document flags, duplicate counts, totals, and `/summary_matrix.csv`; aggregate summary remains as `summary_mode=aggregate` | Sticky columns, dependent selects, and PDF parity still deferred | Stage 3J plus Iteration 3 and later PDF stage | no | no |
| About tab | Form1, StringCipher | Implemented as `/legacy?tab=about` preview/status page | Activation/licensing workflow deferred | Stage 3E | no | no |

## Rewards

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Add reward | Form2, Form3 | Implemented in web dev write mode; form grouped closer to legacy dialog in Stage 3I | Inserts `rewards`, duplicate-number parity still needs refinement | Stage 3C plus Stage 3I | yes | yes |
| Edit reward | Form2, Form3 | Implemented in web dev write mode; form grouped closer to legacy dialog in Stage 3I | Updates classification, price, stock, links, dates | Stage 3C plus Stage 3I | yes | yes |
| Delete reward | Form2 | Implemented in web dev write mode | Deletes DB row only; media folders/files are preserved | Stage 3C | yes | yes |
| Reward photos | Form3, Form4 | Upload/replace, clipboard paste, clear/unlink, and zoom/pan large viewer implemented in web dev write mode | Physical file deletion still deferred; Clipboard API needs Windows browser QA | Stage 3F plus Iteration 4 and later photo deletion stage | yes | yes |

## Marks

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Add mark | Form1, Form3 | Implemented in web dev write mode; form grouped closer to legacy dialog in Stage 3I | Inserts `mark`, duplicate-number parity still needs refinement | Stage 3D plus Stage 3I | yes | yes |
| Edit mark | Form3 | Implemented in web dev write mode; form grouped closer to legacy dialog in Stage 3I | Updates classification, price, stock, links, dates | Stage 3D plus Stage 3I | yes | yes |
| Delete mark | Form1, Form3 | Implemented in web dev write mode | Deletes DB row only; SourceMark folders/files are preserved | Stage 3D | yes | yes |
| Mark photos | Form3, Form4 | Upload/replace, clipboard paste, clear/unlink, and zoom/pan large viewer implemented in web dev write mode | Physical file deletion still deferred; Clipboard API needs Windows browser QA | Stage 3F plus Iteration 4 and later photo deletion stage | yes | yes |

## Guides

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Rank guide CRUD | Form5 | Implemented in web dev write mode on `/guides`; form links jump to the rank block and return back to the source form | Person rank references can become invalid if protection is bypassed | Stage 3H plus Iteration 2 | yes | yes |
| Reward tree guide CRUD | Form6 | Implemented in web dev write mode for `guide_lev_0` through `guide_lev_4`; form links jump to the shared reward/mark guide tree and return back to the source form | Rewards/marks references and `id_link` backfill can change | Stage 3H plus Iteration 2 | yes | yes |

## Photos

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Upload from file | Form2, Form3 | Implemented in web dev write mode for person/reward/mark photo fields | Copies real media into Source/SourceMark; backup required | Stage 3F | yes | yes |
| Paste from clipboard equivalent | Form2, Form3 | Implemented in write mode through browser Clipboard API and the existing guarded upload endpoint | Browser support must be verified on owner Windows; file upload remains fallback | Iteration 4 | yes | yes |
| Replace | Form2, Form3 | Implemented as upload with generated safe filename and DB field update | Old physical file remains on disk | Stage 3F | yes | yes |
| Delete | Form2, Form3 | Implemented as clear/unlink of DB field only | Physical delete can break historical records and remains deferred | Later restore-safe photo delete stage | yes | yes |

## PDF

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Person PDF | Form1, Form7, CreatePDF | Not implemented | Reads personal/media data, writes generated PDF outside DB | Stage 3G | no for read-only export | no |
| Summary PDF | Form1, Form8, CreatePDF | Not implemented | Output validation against legacy layout needed | Stage 3G | no for read-only export | no |

## Search / Filter / Svod

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Legacy filters | Form1 | Search filters implemented for all/persons/rewards/marks; empty specific-category searches show all category records; main rewards screen filters implemented for rank and reward guide levels | Dependent select narrowing and database-backed suggestions are still deferred | Stage 3G plus Iterations 1-2 | no | no |
| Search CSV export | Form1 | Implemented as read-only `/search.csv` | Output parity with legacy export can still be refined | Stage 3G | no | no |
| Summary CSV export | Form1 | Implemented as read-only `/summary_matrix.csv` for the кавалеры × награды matrix and `/summary.csv` for aggregate summary | PDF export still deferred | Stage 3J plus Iteration 3 | no | no |
| Summary tables | Form1 | Implemented with guide-level filters, default person/reward matrix, aggregate fallback mode, optional mark aggregate mode, totals, and CSV exports | Sticky first columns, cascading selects, and further reward-number layout can still be refined | Stage 3J plus Iteration 3 | no | no |

## Activation / Licensing

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Activation/licensing | Form1, StringCipher, activation repo | Deferred | Scenario unclear; may not belong in local mirror | Deferred until clarified | no | no |
