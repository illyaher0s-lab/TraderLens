# SW2014 PIT Taxonomy Audit

**Status:** taxonomy_selection_not_ready  
**Taxonomy:** SW2014 only  
**Audit window:** 20160104 to 20260710

## Full Expected-Universe Check

- Checked trade days: 2554
- Daily stock-days read: 10,901,549
- Expected listed daily stock-days: 10,826,861
- Excluded before listing: 71,035
- Excluded after delisting: 0
- Missing lifecycle: 3,653
- Blocking gaps: 7311

## Frozen Candidate Policy

- Taxonomy source: SW2014 only
- PIT rule: `in_date <= as_of_date AND (out_date IS NULL OR out_date >= as_of_date)`
- Policy hash: `19b313956b7f054f9164f46b4eacb2b23f0b19398a8c1ee10da2eb26252cf8cd`
- Selected partitions: 53 with SHA-256 in the selection manifest

## First Blocking Gap

20160104: 3 daily stocks missing lifecycle

This is a full taxonomy-selection audit only; it does not run formal qualification.
