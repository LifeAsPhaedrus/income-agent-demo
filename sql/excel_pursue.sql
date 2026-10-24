-- Append-only feed schema preserves existing connected workbook columns.
CREATE OR REPLACE VIEW public.excel_pursue AS
SELECT g.id AS listing_id,
       g.record->>'title' AS title,
       coalesce(g.record->>'url','https://www.freelancer.com/projects/' || split_part(g.id, ':', 2)) AS listing_url,
       g.record->'budget'->>'currency' AS currency,
       CASE WHEN jsonb_typeof(g.record->'budget'->'minimum') = 'number'
            THEN (g.record->'budget'->>'minimum')::numeric END AS minimum_budget,
       CASE WHEN jsonb_typeof(g.record->'budget'->'maximum') = 'number'
            THEN (g.record->'budget'->>'maximum')::numeric END AS maximum_budget,
       g.record->'budget'->>'type' AS project_type,
       g.record->>'pay' AS hourly_assessment,
       g.record->>'note' AS review_notes,
       g.record->>'description' AS description,
       g.synced_at AS database_updated_at,
       (p.record->'draft'->>'amount')::numeric AS proposed_bid_amount,
       p.record->'draft'->>'currency' AS proposed_bid_currency,
       (p.record->'draft'->'terms'->>'days')::integer AS delivery_days,
       CASE WHEN p.record->'draft'->'terms'->>'days' IS NOT NULL
            THEN 'After receiving the required files and confirming the agreed scope' END AS delivery_start_condition,
       (p.record->'draft'->'terms'->>'revision_rounds')::integer AS revision_rounds,
       p.version AS proposal_version,
       p.record->'draft'->>'body' AS proposal_text,
       CASE b.record->>'state'
            WHEN 'rejected' THEN 'Not submitted - rejected by Freelancer'
            WHEN 'submitted' THEN 'Submitted'
            WHEN 'existing' THEN 'Existing bid found on Freelancer'
            WHEN 'unknown' THEN 'Outcome uncertain - check Freelancer'
            WHEN 'submitting' THEN 'Attempt started - check Freelancer before retry'
            ELSE CASE WHEN p.version IS NULL THEN 'No proposal drafted' ELSE 'Draft - not submitted' END END AS bid_status,
       b.record->>'message' AS bid_status_detail,
       b.record->>'bid_id' AS freelancer_bid_id,
       (b.record->'payload'->>'amount')::numeric AS attempted_bid_amount,
       (b.record->'payload'->>'milestone_percentage')::integer AS attempted_milestone_percentage,
       (b.record->>'version')::integer AS attempted_proposal_version,
       b.updated_at AS bid_status_updated_at,
       CASE WHEN g.id LIKE 'freelancer:%' THEN 'http://127.0.0.1:8766/proposal.html?id=freelancer%3A' || split_part(g.id, ':', 2) END AS proposal_review_url,
       coalesce(g.record->>'source','Freelancer') AS opportunity_source,
       g.record->>'status' AS review_status,
       g.record->>'salary_text' AS advertised_salary_text,
       g.record->>'location' AS eligible_location,
       g.record->'earnings'->>'gross_basis' AS earnings_basis,
       (g.record->'earnings'->>'gross_amount')::numeric AS estimated_gross_amount,
       (g.record->'earnings'->>'fee_amount')::numeric AS estimated_platform_fee,
       (g.record->'earnings'->>'net_amount')::numeric AS estimated_after_fee_before_tax,
       g.record->'earnings'->>'currency' AS earnings_currency,
       g.record->'earnings'->>'unit' AS earnings_pay_unit,
       g.record->'earnings'->>'fee_policy' AS fee_policy,
       g.record->'earnings'->>'note' AS earnings_limitations,
       g.record->'earnings'->>'policy_url' AS fee_policy_url
FROM public.gigs g
LEFT JOIN LATERAL (SELECT version,record FROM public.proposal_versions WHERE listing_id=g.id ORDER BY version DESC LIMIT 1) p ON true
LEFT JOIN public.bid_submissions b ON b.listing_id=g.id
WHERE g.record->>'url' IS NOT NULL AND g.record->>'status' = 'saved';
COMMENT ON VIEW public.excel_pursue IS 'Pursue selections with latest draft and separate last bid attempt. Rejected does not mean submitted. Review edits belong in the agent app.';
