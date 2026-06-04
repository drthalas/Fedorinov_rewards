# Legacy Feature Gap

Stage 3 changes the target from a read-only viewer toward a full functional legacy mirror on the safe development data root. Write features must remain blocked until a fresh backup exists and `WRITE_MODE=true` is explicitly enabled.

## Persons

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Add person | Form1, Form2 | Implemented in web dev write mode | Creates `person` row and media folder expectations | Stage 3B | yes | yes |
| Edit person | Form2 | Implemented in web dev write mode | Changes personal fields, links, comments, rank, dates | Stage 3B | yes | yes |
| Delete person | Form1, Form2 | Implemented in web dev write mode; blocks delete while rewards exist | May orphan rewards/media if parity is expanded later | Stage 3B | yes | yes |
| Person photos | Form2, Form4 | Upload/replace and clear/unlink implemented in web dev write mode; viewer/slideshow implemented | Physical file deletion and clipboard paste still deferred | Stage 3F plus later photo deletion/paste stage | yes | yes |

## Legacy Desktop Layout

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Main desktop shell | Form1 | Implemented as `/legacy` separate route | Layout parity only; no direct writes | Stage 3E | no | no |
| Rewards tab layout | Form1 | Implemented as `/legacy?tab=rewards` using existing guarded CRUD links | Delete controls must remain POST-only and write-mode gated | Stage 3E | only for writes | only for writes |
| Search tab layout | Form1 | Reworked in Stage 3G with category, condition, value, grouped result tables, counts, and reset | Context auto-submit JS still deferred | Stage 3G plus later UI polish | no | no |
| Marks tab layout | Form1 | Implemented as `/legacy?tab=marks` using existing guarded CRUD links | Delete controls must remain POST-only and write-mode gated | Stage 3E | only for writes | only for writes |
| Summary tab basic aggregates | Form1 | Implemented as `/legacy?tab=summary` basic counts/sums | Full dynamic matrix/export parity deferred | Stage 3E plus Stage 3H | no | no |
| About tab | Form1, StringCipher | Implemented as `/legacy?tab=about` preview/status page | Activation/licensing workflow deferred | Stage 3E | no | no |

## Rewards

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Add reward | Form2, Form3 | Implemented in web dev write mode | Inserts `rewards`, duplicate-number parity still needs refinement | Stage 3C | yes | yes |
| Edit reward | Form2, Form3 | Implemented in web dev write mode | Updates classification, price, stock, links, dates | Stage 3C | yes | yes |
| Delete reward | Form2 | Implemented in web dev write mode | Deletes DB row only; media folders/files are preserved | Stage 3C | yes | yes |
| Reward photos | Form3, Form4 | Upload/replace and clear/unlink implemented in web dev write mode; large viewer implemented | Physical file deletion and clipboard paste still deferred | Stage 3F plus later photo deletion/paste stage | yes | yes |

## Marks

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Add mark | Form1, Form3 | Implemented in web dev write mode | Inserts `mark`, duplicate-number parity still needs refinement | Stage 3D | yes | yes |
| Edit mark | Form3 | Implemented in web dev write mode | Updates classification, price, stock, links, dates | Stage 3D | yes | yes |
| Delete mark | Form1, Form3 | Implemented in web dev write mode | Deletes DB row only; SourceMark folders/files are preserved | Stage 3D | yes | yes |
| Mark photos | Form3, Form4 | Upload/replace and clear/unlink implemented in web dev write mode; large viewer implemented | Physical file deletion and clipboard paste still deferred | Stage 3F plus later photo deletion/paste stage | yes | yes |

## Guides

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Rank guide CRUD | Form5 | Implemented in web dev write mode on `/guides`; delete is blocked while person cards use the value | Person rank references can become invalid if protection is bypassed | Stage 3H | yes | yes |
| Reward tree guide CRUD | Form6 | Implemented in web dev write mode for `guide_lev_0` through `guide_lev_4`; delete is blocked for nodes with children or reward/mark references | Rewards/marks references and `id_link` backfill can change | Stage 3H | yes | yes |

## Photos

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Upload from file | Form2, Form3 | Implemented in web dev write mode for person/reward/mark photo fields | Copies real media into Source/SourceMark; backup required | Stage 3F | yes | yes |
| Paste from clipboard equivalent | Form2, Form3 | UI placeholder and implementation plan documented | Needs browser Clipboard API and owner QA of upload flow first | Later Stage 3F follow-up | yes | yes |
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
| Legacy filters | Form1 | Search filters implemented for all/persons/rewards/marks and contains/starts/exact | Full legacy svod/filter matrix still deferred | Stage 3G plus Stage 3H | no | no |
| Search CSV export | Form1 | Implemented as read-only `/search.csv` | Output parity with legacy export can still be refined | Stage 3G | no | no |
| Summary tables | Form1 | Dashboard counts only | Aggregate parity and export expectations | Stage 3H | no | no |

## Activation / Licensing

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Activation/licensing | Form1, StringCipher, activation repo | Deferred | Scenario unclear; may not belong in local mirror | Deferred until clarified | no | no |
