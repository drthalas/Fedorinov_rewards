# Legacy Feature Gap

Stage 3 changes the target from a read-only viewer toward a full functional legacy mirror on the safe development data root. Write features must remain blocked until a fresh backup exists and `WRITE_MODE=true` is explicitly enabled.

## Persons

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Add person | Form1, Form2 | Not implemented | Creates `person` row and media folder expectations | Stage 3B | yes | yes |
| Edit person | Form2 | Not implemented | Changes personal fields, links, comments, rank, dates | Stage 3B | yes | yes |
| Delete person | Form1, Form2 | Not implemented | May orphan rewards/media or delete connected rows | Stage 3B after validation | yes | yes |
| Person photos | Form2, Form4 | Read-only display only | File copy/replace/delete and path updates | Stage 3F | yes | yes |

## Rewards

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Add reward | Form2, Form3 | Implemented in web dev write mode | Inserts `rewards`, duplicate-number parity still needs refinement | Stage 3C | yes | yes |
| Edit reward | Form2, Form3 | Implemented in web dev write mode | Updates classification, price, stock, links, dates | Stage 3C | yes | yes |
| Delete reward | Form2 | Implemented in web dev write mode | Deletes DB row only; media folders/files are preserved | Stage 3C | yes | yes |
| Reward photos | Form3, Form4 | Read-only display only | Upload/replace/delete and path management deferred | Stage 3F | yes | yes |

## Marks

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Add mark | Form1, Form3 | Implemented in web dev write mode | Inserts `mark`, duplicate-number parity still needs refinement | Stage 3D | yes | yes |
| Edit mark | Form3 | Implemented in web dev write mode | Updates classification, price, stock, links, dates | Stage 3D | yes | yes |
| Delete mark | Form1, Form3 | Implemented in web dev write mode | Deletes DB row only; SourceMark folders/files are preserved | Stage 3D | yes | yes |

## Guides

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Rank guide CRUD | Form5 | Read-only `/guides` section | Person rank references can become invalid | Stage 3E | yes | yes |
| Reward tree guide CRUD | Form6 | Read-only collapsible tree | Rewards/marks references and `id_link` backfill can change | Stage 3E | yes | yes |

## Photos

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Upload from file | Form2, Form3 | Not implemented | Copies real media into Source/SourceMark | Stage 3F | yes | yes |
| Paste from clipboard equivalent | Form2, Form3 | Not implemented | Needs browser upload workflow, no direct clipboard file writes first | Stage 3F or later | yes | yes |
| Replace | Form2, Form3 | Not implemented | Existing path/file may be overwritten | Stage 3F | yes | yes |
| Delete | Form2, Form3 | Not implemented | Removing files can break historical records | Stage 3F after restore test | yes | yes |

## PDF

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Person PDF | Form1, Form7, CreatePDF | Not implemented | Reads personal/media data, writes generated PDF outside DB | Stage 3G | no for read-only export | no |
| Summary PDF | Form1, Form8, CreatePDF | Not implemented | Output validation against legacy layout needed | Stage 3G | no for read-only export | no |

## Search / Filter / Svod

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Legacy filters | Form1 | Basic search only | Query parity and protected-field display rules | Stage 3H | no | no |
| Summary tables | Form1 | Dashboard counts only | Aggregate parity and export expectations | Stage 3H | no | no |

## Activation / Licensing

| Feature | Legacy source/form | Current web status | Risk | Recommended stage | Requires backup? | Requires write mode? |
| --- | --- | --- | --- | --- | --- | --- |
| Activation/licensing | Form1, StringCipher, activation repo | Deferred | Scenario unclear; may not belong in local mirror | Deferred until clarified | no | no |
