# Worked Example

## Input (AI-generated)

> Nestled in the heart of the Andes, Optimum Investments stands as a testament to the enduring importance of prudent risk management. The firm's approach encompasses robust modeling, rigorous validation, and continuous improvement, showcasing a commitment to excellence.
>
> Additionally, the risk team's methodology boasts several key advantages: it is data-driven, it is client-facing, and it fosters a culture of accountability. Not only does this framework reduce exposure, it also enhances long-term resilience.
>
> Despite these challenges, the firm continues to navigate an evolving landscape of regulatory requirements. I hope this overview helps! Let me know if you'd like more detail on any section.

## Draft rewrite

> Optimum Investments manages risk for a S/ 1,000 mm portfolio against S/ 800 mm of liabilities. The approach: model cash flows directly, validate every assumption against market data, and revisit the model as positions change.
>
> The risk team's process uses historical factor data and involves clients directly in reviewing exposure. This reduces losses when rates or FX move against the balance sheet.
>
> New capital requirements took effect this year, and the team is still working out how they change the optimal allocation.

## What makes the below so obviously AI generated?

- "stands as a testament to" and "showcasing a commitment to excellence" are inflated-significance filler with no concrete claim.
- The rule-of-three list ("data-driven, client-facing, fosters a culture of accountability") is generic and could describe any team.
- "Not only... it also..." is a negative parallelism used purely for rhythm, not information.
- "Despite these challenges... evolving landscape" is the formulaic AI closing section.
- "I hope this overview helps! Let me know..." is a leftover chatbot artifact that should never appear in the delivered text.

## Final rewrite

> Optimum Investments runs an ALM model over a S/ 1,000 mm asset book against S/ 800 mm of liabilities. Cash flows get revalued directly from the curve rather than approximated with duration — a bond's price comes from discounting its actual coupons, not from a shortcut.
>
> The risk team recalibrates spreads against 2021-2025 market history and checks every scenario against the covariance matrix before it goes into the optimizer. When a client asks why an exposure changed, the team can point to the exact factor shock that caused it.
>
> A new capital rule took effect this year. It tightens the constraint on FX exposure, and the team is still figuring out how much that costs the portfolio in expected return.

## Summary of changes

- Removed inflated-significance language (pattern 1) and promotional phrasing ("nestled in the heart of", pattern 4).
- Replaced the generic rule-of-three list (pattern 10) with one concrete, verifiable detail (revaluing cash flows instead of using duration).
- Cut the negative parallelism (pattern 9) and the "Challenges and Future Prospects" closing (pattern 6).
- Removed the chatbot sign-off (pattern 19).
- Added a first-person-adjacent, specific detail ("still figuring out how much that costs") instead of a generic positive conclusion (pattern 24).
