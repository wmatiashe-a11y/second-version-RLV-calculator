def calculate_metrics(
    land, ff, bonus, ih, m_price, c_cost,
    heritage_on=False,
    heritage_approvals_assumed=False,
    heritage_cost_uplift=0,
    heritage_fees_uplift=0,
    heritage_profit_uplift=0,
):
    # ---- Cape Town HPOZ logic (policy-aligned) ----
    # HPOZ does not automatically grant extra rights; it triggers approval for certain activities.
    # Conservative assumption: if HPOZ applies and approvals are NOT assumed, density bonus is treated as not achievable.
    effective_bonus = bonus
    if heritage_on and not heritage_approvals_assumed:
        effective_bonus = 0

    # 1) Bulk
    total_bulk = (land * ff) * (1 + (effective_bonus / 100.0))

    # 2) IH split
    ih_bulk = total_bulk * (ih / 100.0)
    market_bulk = total_bulk - ih_bulk

    # 3) Revenue
    gdv = (market_bulk * m_price) + (ih_bulk * IH_CAP_PRICE)

    # 4) Dev charges (assumed chargeable on market bulk)
    dev_charges = market_bulk * DC_RATE

    # 5) Costs
    used_cost = c_cost * (1 + (heritage_cost_uplift / 100.0)) if heritage_on else c_cost
    construction = total_bulk * used_cost

    base_fee_rate = 0.125
    fee_rate = base_fee_rate * (1 + (heritage_fees_uplift / 100.0)) if heritage_on else base_fee_rate
    fees = construction * fee_rate

    base_profit_rate = 0.20
    profit_rate = base_profit_rate * (1 + (heritage_profit_uplift / 100.0)) if heritage_on else base_profit_rate
    profit_target = gdv * profit_rate

    # 6) Residual
    rlv = gdv - construction - dev_charges - fees - profit_target
    return rlv, total_bulk, dev_charges, gdv, ih_bulk
