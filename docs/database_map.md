# Database Map

This map is based on read-only schema inspection and legacy code review. It does not include real row contents.

## Storage

- Database: `${REWARDS_DATA_DIR}/database/MyDatabase.sqlite`
- Person media: `${REWARDS_DATA_DIR}/Source`
- Standalone mark media: `${REWARDS_DATA_DIR}/SourceMark`
- Fallback/support files: `${REWARDS_DATA_DIR}/default`

## `person`

- Purpose: One awarded person/cavalier record.
- Key fields: `id`, `fio`, `birthday`, `id_rank`, `link1`, `link2`, `comment`.
- Media path fields: `person_foto`, `main_foto`, `rewards_foto`, `book1_foto`, `book2_foto`, `card1_foto`, `card2_foto`.
- Relationships: `id_rank` references `guide.id`; `rewards.person_id` references `person.id`.
- Potentially personal fields: `fio`, `birthday`, `link1`, `link2`, `comment`, person/card/book photos.
- Safe Stage 2 fields: Internal id, rank label, aggregate counts, photo presence flags, media thumbnails only when requested through safe local endpoint.
- Protected block: Full name, birthday, links, comments, and personal document photos.

## `rewards`

- Purpose: Awards attached to a person.
- Key fields: `id`, `person_id`, `id_gos`, `id_catigory`, `id_sub_catigory`, `id_name`, `id_link`, `number`, `instock`, `date_purchase`, `price_purchase`, `price_now`.
- Media path fields: `front_foto`, `back_foto`, `book1_foto`, `book2_foto`, `reward_list`.
- Relationships: `person_id` references `person.id`; `id_gos` through `id_name` reference `guide_lev_0` through `guide_lev_3`; `id_link` stores aggregated guide links/text from level 4 in legacy behavior.
- Potentially personal fields: Link text, reward list image, document/book photos, association to person.
- Safe Stage 2 fields: Classification labels, internal id, stock flag, purchase/current price, purchase date, media presence, front/back thumbnails.
- Protected block: Person association details, links, document photos, reward list image, sensitive comments inherited from person.

## `mark`

- Purpose: Standalone marks not attached to a person.
- Key fields: `id`, `id_gos`, `id_catigory`, `id_sub_catigory`, `id_name`, `id_link`, `number`, `instock`, `date_purchase`, `price_purchase`, `price_now`.
- Media path fields: `front_foto`, `back_foto`, `book1_foto`, `book2_foto`.
- Relationships: `id_gos` through `id_name` reference `guide_lev_0` through `guide_lev_3`; `id_link` stores aggregated guide links/text from level 4 in legacy behavior.
- Potentially personal fields: Usually less personal than `person` and `rewards`, but links and document/book photos can still expose sensitive source details.
- Safe Stage 2 fields: Classification labels, internal id, number, stock flag, purchase/current price, purchase date, front/back thumbnails.
- Protected block: Link text and book/document photos until explicit display rules are decided.

## `guide`

- Purpose: Flat guide for ranks/titles assigned to persons.
- Key fields: `id`, `name`.
- Media path fields: None.
- Relationships: `person.id_rank` references `guide.id`.
- Potentially personal fields: None expected, but labels should still be treated as local collection metadata.
- Safe Stage 2 fields: `id`, `name`.
- Protected block: None expected.

## `guide_lev_0`

- Purpose: Top level of award/mark hierarchy, used as state/country/group.
- Key fields: `id`, `idl`, `name`.
- Media path fields: None.
- Relationships: Parent root uses `idl = -1`; `guide_lev_1.idl` points to this table.
- Potentially personal fields: None expected.
- Safe Stage 2 fields: `id`, `name`, child count.
- Protected block: None expected.

## `guide_lev_1`

- Purpose: Category level under `guide_lev_0`.
- Key fields: `id`, `idl`, `name`.
- Media path fields: None.
- Relationships: `idl` references `guide_lev_0.id`; `guide_lev_2.idl` points to this table.
- Potentially personal fields: None expected.
- Safe Stage 2 fields: `id`, `name`, parent id, child count.
- Protected block: None expected.

## `guide_lev_2`

- Purpose: Subcategory level under `guide_lev_1`.
- Key fields: `id`, `idl`, `name`.
- Media path fields: None.
- Relationships: `idl` references `guide_lev_1.id`; `guide_lev_3.idl` points to this table.
- Potentially personal fields: None expected.
- Safe Stage 2 fields: `id`, `name`, parent id, child count.
- Protected block: None expected.

## `guide_lev_3`

- Purpose: Award/mark name level under `guide_lev_2`.
- Key fields: `id`, `idl`, `name`.
- Media path fields: None.
- Relationships: `idl` references `guide_lev_2.id`; `rewards.id_name` and `mark.id_name` point to this table; `guide_lev_4.idl` points to this table.
- Potentially personal fields: None expected.
- Safe Stage 2 fields: `id`, `name`, parent id, reward count, mark count.
- Protected block: None expected.

## `guide_lev_4`

- Purpose: Link/source text level under an award/mark name.
- Key fields: `id`, `idl`, `name`.
- Media path fields: None.
- Relationships: `idl` references `guide_lev_3.id`; legacy Form6 aggregates these values into `rewards.id_link` and `mark.id_link`.
- Potentially personal fields: Link/source text can expose collection research sources.
- Safe Stage 2 fields: Presence/count of links.
- Protected block: Full link/source values until link display rules are decided.

## `logs`

- Purpose: Legacy application event log.
- Key fields: `datetime`, `action`, `comment`.
- Media path fields: None.
- Relationships: None.
- Potentially personal fields: `comment` may contain IDs, SQL text, errors, or user-entered details.
- Safe Stage 2 fields: Aggregate counts only.
- Protected block: Full log rows.

## Media Path Fields

- Person media: `person.person_foto`, `person.main_foto`, `person.rewards_foto`, `person.book1_foto`, `person.book2_foto`, `person.card1_foto`, `person.card2_foto`.
- Reward media: `rewards.front_foto`, `rewards.back_foto`, `rewards.book1_foto`, `rewards.book2_foto`, `rewards.reward_list`.
- Mark media: `mark.front_foto`, `mark.back_foto`, `mark.book1_foto`, `mark.book2_foto`.

Stage 2 should resolve media paths only inside `REWARDS_DATA_DIR`, with fallback to `default/nofoto.jpg` where appropriate.
