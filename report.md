# Building an Agentic Trading System Using TradingAgents and Robinhood MCP

This document outlines how to construct a research and execution platform that combines TauricResearch’s **TradingAgents** framework with Robinhood’s newly‑launched **Agentic Trading** infrastructure, a custom stock momentum model and various market data APIs.  The goal is to emulate the roles of a fundamental research desk, quant desk, portfolio manager and risk officer within one cohesive system.  Throughout this document, lines from external sources are cited with tether IDs (e.g. `【46718602198144†L82-L88】`); these citations correspond to the browser snapshots taken during the research phase.

## 1. Background and Constraints

### 1.1 Robinhood Agentic Trading

Robinhood announced a Model Context Protocol (MCP) that lets external AI agents interact with Robinhood accounts.  The public beta requires users to open a **dedicated agentic trading account**.  This account is separate from a user’s normal brokerage portfolio and restricts the agent to only the funds allocated there.  Robinhood sends push notifications when an agent makes a trade and provides real‑time visibility into trading activity【46718602198144†L82-L88】.  In the 2026 beta, only **equities** can be traded via MCP; options, crypto and other instruments are not yet supported【46718602198144†L82-L88】.  Robinhood plans to add options, futures and other assets later.  Because this is a new, lightly regulated capability, Robinhood includes built‑in guardrails such as spending limits, trade previews and manual approvals【46718602198144†L104-L110】.

**Key constraints:**

* The agent must trade only within the dedicated agentic account.  Direct access to a Roth IRA or other personal accounts is not provided【46718602198144†L82-L88】.  For now, the IRA should be monitored and rebalancing recommendations should be generated, but live execution should be manual until Robinhood expands support.
* Only long equity orders are allowed in the beta.  Short selling, margin trading, options and derivatives are outside the scope of current MCP support【46718602198144†L82-L88】.
* Robinhood emphasises that agentic trading carries risks.  Manual approval, trade previews and fraud detection are built in to mitigate unintended trades【46718602198144†L104-L110】.

### 1.2 TradingAgents Framework

**TradingAgents** is an open‑source multi‑agent LLM trading framework designed for research purposes.  It mirrors the structure of a professional trading firm by decomposing complex tasks into specialized agents.  The framework deploys separate large‑language‑model agents for **fundamental analysis, sentiment analysis, news analysis and technical analysis**; their outputs feed into a bull/bear **researcher team** that debates trade theses【770496408791981†L348-L353】.  A **trader agent** synthesizes these reports to recommend orders, while a **risk management team** evaluates volatility, liquidity and other risk factors.  A **portfolio manager** (LLM or human) approves or rejects the proposed trades【770496408791981†L367-L403】.  The authors stress that the framework is for research, not financial advice【770496408791981†L357-L361】.

The repository supports installation via `pip` or Docker and can be configured to use different LLM providers (OpenAI, Google, Anthropic, etc.) as well as data sources such as Alpha Vantage.  Running `tradingagents` in interactive CLI mode allows you to specify tickers, research depth and analysis date【770496408791981†L409-L476】.  When incorporated into our system, TradingAgents will act as the **research desk** to generate trade theses and recommendations.

### 1.3 Market Data and Licensing

Real‑time and 15‑minute delayed U.S. stock market data is **regulated by stock exchanges, FINRA and the SEC**.  Data providers must be licensed by the exchanges before distributing this information【488940942997951†L18-L27】.  Alpha Vantage is an exchange‑licensed provider and cautions against using “free” providers that scrape or redistribute data illegally【488940942997951†L18-L27】.  In the system described here, Alpha Vantage will be used for historical and, if needed, licensed real‑time data.  Other data sources include:

* **SEC EDGAR API** for company filings and fundamental data.
* **FRED** for macroeconomic time series (interest rates, inflation, unemployment).
* **Finnhub** or other secondary providers for supplementary quotes, news and sentiment.

These sources complement Robinhood’s MCP data (positions, buying power, account balances, tradability and order previews).

### 1.4 Custom Stock Momentum Prediction Model

The custom momentum model developed previously combines multiple features into a logistic‑sigmoid‑based score.  At each time \(t\) it calculates:

\[
Z_t = 0.40 P_t + 0.20 T_t + 0.10 R_t + 0.10 V_t + 0.15 S_t + 0.05 F_t,
\]

where

* \(P_t\) – recent price trend (e.g., moving‑average slope or relative strength).
* \(T_t\) – technical indicator state (e.g., MACD, RSI).
* \(R_t\) – risk penalty (volatility or drawdown).
* \(V_t\) – volume confirmation (volume relative to its moving average).
* \(S_t\) – social/sentiment attention (news sentiment, StockTwits/Reddit activity).
* \(F_t\) – fundamental factor (e.g., earnings surprises or valuation ratios).

The momentum score is then computed as

\[
\text{MomentumScore}_t = \frac{100}{1 + e^{-1.6 Z_t}},
\]

which scales \(Z_t\) to a 0–100 range.  Scores below 40 suggest bearish or avoid trades; 40–60 is neutral; 60–75 qualifies for deeper research; 75–90 is a strong candidate; 90–100 indicates high conviction but higher risk due to crowding.  **The model is only one input** into the decision process and must pass rigorous validation before influencing live trades.

## 2. System Architecture

The system is designed to behave like a miniature investment firm.  The diagram below illustrates the flow of information and responsibilities.  Each component is implemented as a module or service in the repository.

```mermaid
flowchart TD
    A[Market Scheduler\nmarket open/close\nrebalancing windows] --> B[Universe Selector\n(watchlists, ETFs, holdings)]
    B --> C[Market Data Layer]
    C --> C1[Robinhood MCP: positions, buying power, quotes, tradability]
    C --> C2[Alpha Vantage / licensed market data]
    C --> C3[SEC EDGAR: fundamentals]
    C --> C4[FRED: macro series]
    C --> C5[Finnhub (optional)]
    C --> D[Feature Store (DuckDB/Postgres)]
    D --> E[Momentum Model]
    D --> F[TradingAgents Research Graph]
    E --> G[Signal Validation Layer]
    F --> H[Bull/Bear Debate & Trade Thesis]
    G --> I[Portfolio Policy Engine]
    H --> I
    I --> J[Risk Engine: sizing, liquidity, limits]
    J --> K{Approval Gate}
    K -->|Reject| L[Log decision & rationale]
    K -->|Review-only| M[Send plan to user]
    K -->|Approved| N[Execution Gateway]
    N --> O[Review order via Robinhood MCP]
    O --> P{Pre‑trade warnings?}
    P -->|Yes| L
    P -->|No| Q[Place order via MCP]
    Q --> R[Post‑Trade Monitor\nfills, P&L, exposure]
    R --> S[Decision Journal & feedback loop]
    S --> F
```

**Data flow summary:**

1. A scheduler triggers the universe selector at market open/close and on defined rebalancing periods.
2. The universe selector compiles watchlists (e.g., major ETFs, sector ETFs, current holdings) and passes them to the market data layer.
3. The data layer fetches account context from Robinhood’s MCP (positions, buying power, tradability), historical prices from Alpha Vantage and other sources, fundamental data from SEC EDGAR and macro series from FRED.
4. Data is stored in a feature store (DuckDB or Postgres).  Feature engineering pipelines compute momentum model inputs and other signals.
5. TradingAgents (research desk) consumes this data and runs specialized LLM agents (fundamental, sentiment, news and technical analysts) that feed into bull and bear researchers who debate trade theses【770496408791981†L348-L353】.  The trader agent summarises the debate into a proposal, while the risk and portfolio manager agents evaluate risk【770496408791981†L367-L403】.
6. The custom momentum model scores each candidate and its validation module checks for drift, calibration and performance relative to benchmarks.  Only validated signals proceed.
7. A portfolio policy engine (user‑configurable) decides whether the trade fits account objectives (e.g., slow IRA rebalancing vs. tactical trades) and passes candidates to the risk engine.
8. The risk engine enforces position sizing rules, liquidity filters, exposure and drawdown limits, tax‑aware checks (wash‑sale rules) and kill switches.
9. Orders that pass risk checks are reviewed via Robinhood MCP’s `review_equity_order` endpoint, which returns pre‑trade warnings or errors.  If warnings occur (e.g., insufficient buying power or unsettled funds), the order is cancelled and logged.
10. When all checks pass, the system places a limit order via `place_equity_order`.  Post‑trade monitoring records fills, slippage, updated exposures and feeds outcomes back into the research agents for continuous learning.

## 3. Repository Structure

Organize the project as a monorepo with clear separation of concerns.  Below is a suggested layout:

```
robinhood-agentic-trading-system/
  docker/
    Dockerfile              # base image with Python, TradingAgents and dependencies
    docker-compose.yml      # orchestrates services (agent, redis, etc.)
    entrypoint.sh           # startup script

  app/
    main.py                # orchestrates scheduler and pipeline
    config.py              # environment variables, keys, run configuration
    scheduler.py           # cron‑like scheduler
    logging_config.py      # structured logging setup

  integrations/
    robinhood_mcp/
      client.py            # low‑level MCP API calls (auth, account data)
      execution_gateway.py # order review & placement with guardrails
    alpha_vantage/
      client.py
      price_loader.py
      sentiment_loader.py
    sec_edgar/
      client.py
      fundamentals_loader.py
    fred/
      client.py
      macro_loader.py
    finnhub/
      client.py            # optional backup data

  research/
    tradingagents_adapter.py  # wrapper for TradingAgents integration
    prompts/
      system_policy.md        # high‑level agent instructions (e.g., compliance)
      roth_ira_policy.md      # IRA‑specific guidelines
      taxable_policy.md       # taxable account rules (wash sale, holding periods)
      day_trading_policy.md   # day‑trading guidelines
      options_research_policy.md # placeholder until options support arrives

  quant/
    momentum_model/
      features.py             # compute P_t, T_t, R_t, etc.
      scoring.py              # compute Z_t and momentum score
      validation.py           # walk‑forward tests, drift detection
      backtest.py             # backtest strategies vs. benchmarks
    technicals.py             # generic technical indicators
    factor_checks.py          # cross‑sectional factors (size, value, momentum)
    regime_detection.py       # macro regime classification

  portfolio/
    account_policy.py         # account objectives and restrictions
    target_allocations.py     # desired ETF/sector weights
    rebalancer.py             # compute trades to rebalance portfolios
    tax_lot_logic.py          # track lots for taxable accounts
    wash_sale_guard.py        # identify wash‑sale conflicts

  risk/
    pre_trade_checks.py       # consolidated risk checks
    position_sizing.py        # risk‑based position sizing algorithms
    exposure_limits.py        # max weight per name/sector
    drawdown_limits.py        # stop trading if drawdown threshold hit
    liquidity_filters.py      # avoid thinly traded stocks
    kill_switch.py            # emergency stop for anomalies

  execution/
    order_models.py           # data classes for orders
    order_router.py           # route orders to MCP
    order_review.py           # call MCP review endpoint
    order_monitor.py          # monitor order status and fills

  storage/
    schema.sql                # database schema definitions
    migrations/
    duckdb_store.py           # local DuckDB interface
    audit_log.py              # write immutable audit logs

  notebooks/
    model_validation.ipynb    # Jupyter analysis of model performance
    strategy_backtests.ipynb  # strategy backtesting and benchmarking

  tests/
    test_momentum_model.py
    test_risk_limits.py
    test_order_blocking.py
    test_robinhood_mcp_mock.py

  docs/
    architecture.md           # extended design docs
    deployment.md             # AWS deployment steps
    operating_manual.md       # instructions for running and monitoring the system
    risk_policy.md            # risk management framework
```

## 4. AWS Deployment Specification

### 4.1 Instance Sizing and Pricing

Deploy the system on a low‑cost but sufficiently powerful EC2 instance.  **T4g (Graviton2) instances** offer attractive price/performance for always‑on workloads.  According to the Vantage instance database, a `t4g.large` provides 2 vCPUs, 8 GiB of memory and up to 5 Gbps network bandwidth, starting at **$0.0672 per hour**【967698630711914†L22-L24】.  This equates to roughly USD 49.06 per month when running continuously (0.0672 × 730 hours/month).  A `t4g.medium` costs $0.0336/hour (~$24.53/month) and a `t4g.small` costs $0.0168/hour (~$12.26/month) but offer only 4 GiB and 2 GiB of RAM respectively.  For research‑only prototypes, `t4g.medium` is feasible; however, the production system that runs TradingAgents, backtests and data pipelines concurrently should use **t4g.large**.

AWS extends a **T4g free‑trial** through 31 December 2026, which allows up to 750 hours per month of a `t4g.small` instance free of compute charges【413630833615465†L144-L148】.  This is useful for experimentation or staging but not recommended for production due to limited memory (2 GiB) and CPU credits.  Note that EBS volumes and surplus CPU credits still incur charges【413630833615465†L144-L148】.

For storage, choose an **EBS gp3** volume.  The CloudBolt guide notes that gp3 pricing is **$0.08 per GB‑month**, including 3,000 IOPS and 125 MB/s throughput for free【425935456199332†L246-L264】.  Additional IOPS or throughput can be provisioned separately if needed.  An 80 GB gp3 volume therefore costs about $6.40 per month (80 GB × $0.08/GB‑month).  Snapshots cost an additional $0.05 per GB‑month【425935456199332†L246-L279】.

**Networking and other costs:** assign an Elastic IP only if necessary (public IP addresses cost ~$3.65/month in 2026).  Use AWS Systems Manager Session Manager for secure SSH‑less access.  Offload logs to CloudWatch with a short retention period to minimise cost.

### 4.2 Deployment Architecture

Run the system using **Docker Compose** on the EC2 instance.  The Compose file defines services for:

* **agent** – the main Python application container running the scheduler, data ingestion, TradingAgents integration, momentum model and execution logic.
* **redis** – a lightweight in‑memory queue for scheduling and job management.  For the MVP, avoid Postgres unless necessary; DuckDB and SQLite are used for local storage.
* **watchtower** – an optional container to auto‑update services if images are rebuilt.

Persist data (feature store, audit logs, etc.) on the EBS volume.  Mount `./data` and `./logs` directories into the agent container so they survive container restarts.  Use AWS Secrets Manager or SSM Parameter Store to store API keys (Alpha Vantage, Robinhood credentials, LLM provider keys) and load them in at runtime.

## 5. Risk Management and Safety Controls

Given the high stakes of autonomous trading, the system must implement deterministic guardrails that LLMs cannot override.

1. **Separation of research and execution:** TradingAgents produces **proposals**, not direct orders.  The execution layer implements all risk checks and uses deterministic code to decide whether a trade can proceed.
2. **Mandatory order preview:** Always call `review_equity_order` via the MCP before placing any order.  If the MCP warns of insufficient funds, unsettled cash or other issues, cancel the order.
3. **Limit orders only:** Avoid market orders to reduce slippage and ensure price control.
4. **Position and exposure limits:** Set maximum dollar amounts per security and per sector relative to account equity.  For example, do not allow any single position to exceed 5 % of the dedicated account; adjust these thresholds based on user risk tolerance.
5. **Daily loss limit and kill switch:** Monitor realized and unrealized P&L each day.  If cumulative losses exceed a defined threshold, stop trading for the day or require manual intervention.
6. **Liquidity and tradability filters:** Check average daily volume and bid–ask spreads; avoid thinly traded stocks and securities flagged as non‑tradable via MCP.
7. **Wash‑sale rule:** For taxable accounts, ensure that any trade that realizes a loss does not trigger a wash sale by buying substantially identical securities within ±30 days.
8. **Event risk:** Avoid holding through earnings announcements or major macro events unless explicitly allowed.  Consider gating trades around known event dates.
9. **Audit logging:** Store every proposed trade, underlying data snapshot, model version, LLM prompt and MCP response in an immutable audit log.  This is essential for debugging and compliance.
10. **Human approvals:** In the early phases, require the user to manually approve each trade or to set small dollar limits until confidence is established.  Over time, relax this requirement for lower‑risk trades.

## 6. Development Phases

1. **Research‑only MVP:** Build the data ingestion layer, integrate TradingAgents for research and run your momentum model.  Produce daily research reports and candidate lists without placing any orders.
2. **Shadow trading:** Simulate trades using paper orders.  Record hypothetical fills, slippage and portfolio evolution.  Validate that the momentum model and research combination produces acceptable risk‑adjusted returns compared to benchmarks (e.g., SPY).  Adjust weighting and risk rules accordingly.
3. **Order preview mode:** Connect to Robinhood MCP, but only call `review_equity_order` to see what trades would look like.  Introduce human approvals to test risk checks.  Log warnings and adjust logic.
4. **Limited live trading:** Fund the agentic account with a small amount of capital.  Permit the system to execute long equity trades with strict position limits, stop‑loss triggers and daily loss limits.  Continue to log everything and monitor performance.
5. **Expanded support:** Once Robinhood MCP adds options and supports trading directly in a Roth IRA, implement additional modules (options pricing and Greeks, tax‑advantaged rebalancing).  For options and other derivatives, require separate risk models and additional approvals.

## 7. Conclusion and Next Steps

The system described here combines state‑of‑the‑art language models (via TradingAgents) with robust quantitative signals and deterministic risk controls.  By relying on licensed data providers, carefully validating the momentum model and using Robinhood’s official MCP endpoints, the platform remains within regulatory guidelines.  The modular design allows for incremental enhancements—adding new data sources, risk checks and asset classes as they become available.

Before deploying, you should:

* Register for Robinhood’s agentic trading beta and open a dedicated agentic account.
* Obtain API keys for Alpha Vantage, SEC EDGAR (requires no key), FRED (requires a key) and any other data providers.
* Fork the TradingAgents repository and freeze a known‑good commit to avoid unexpected changes.
* Write unit tests for each module (data ingestion, feature engineering, momentum model, risk engine) and run them automatically with CI.
* Set up monitoring and alerting on the EC2 instance (e.g., CPU usage, memory, network, disk) and on trading metrics (drawdown, P&L).  Consider adding automated backups of the audit log and feature store.

By following the structure and safeguards outlined above, you can build a 24/7 system that analyses markets, plans trades and executes them responsibly—acting as a research analyst, quant analyst, portfolio manager and trader rolled into one.
