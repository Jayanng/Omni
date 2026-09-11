# The problem

## One account, two clocks

A Bitget Unified Trading Account can hold tokenized US stocks (rTokens), crypto perpetuals, and
stablecoins under **one margin engine**. That is the product's advantage and the source of a
specific failure mode.

rTokens track US equities. US equities have opening hours. Crypto does not. So inside a single
account two clocks run at different speeds:

```text
crypto perpetuals     24 / 7 / 365        live PnL, live margin consumption
rToken marks          equity session      volatile during regular hours,
                      + extended hours    thin or stale outside them
cash equity market    closed              the reference price cannot update
```

## The failure mode, as Bitget documents it

From Bitget's own support and academy material:

- During weekends and US market holidays, stock-token index prices **may be fixed** while crypto
  futures PnL and account risk continue updating in real time.
- Frozen prices do not mean frozen risk.
- Stock tokens used as margin are counted at a **collateral-ratio-adjusted** effective value,
  not gross value.
- Collateral ratios can vary by asset, market conditions, liquidity, volatility and platform risk
  controls.
- Liquidation begins when the account margin ratio falls below the maintenance margin rate.
- A US market reopen can produce a gap.

## Why the user loses

```text
Friday close        user holds rTokens as collateral, plus a crypto perpetual

weekend             crypto moves, perp PnL changes, margin is consumed
                    rToken mark barely updates, so the account LOOKS stable

Sunday night        margin ratio is already close to the edge
                    nothing in the account tells the user how close

Monday 09:30 ET     the equity gaps, the effective collateral value drops
                    liquidation can trigger in the first minutes

user                was asleep, or was watching a chart that did not show
                    the interaction between the two legs
```

The user's mistake is not a bad stock pick. It is that **nobody was watching the interaction**
between an rToken collateral leg and a live crypto leg across a session change.

## Why existing tools do not solve it

| Existing thing | Why it does not close the loop |
|---|---|
| Playbook strategies | Optimise entries and exits. They do not treat rToken collateral as margin at risk. |
| GetAgent and generic trading agents | Built around signal generation ("macro event, buy the index"). |
| Portfolio dashboards | Show positions, not the interaction between two margin legs. |
| Exchange margin engine | Authoritative, but passive. It liquidates, it does not advise or act. |
| DeFi collateral monitors | Live on other venues, on other account objects, without rToken collateral inside a Bitget UTA. |
| Manual monitoring | Humans sleep. The dangerous window is exactly when they do. |

## The specific question Omni answers

Bitget's Agentic Trading track names the sub-theme **Cross-Asset Execution Agent**, with the core
question: *how does the agent manage rToken and Crypto positions simultaneously?*

Omni answers it as a risk question, not an alpha question:

> Under an explicit shock scenario, does this account survive the next session change, and if
> not, what is the smallest protective action that materially improves its survival?

## Named user

An active Bitget UTA trader who:

- holds tokenized US stocks as collateral rather than selling them,
- runs crypto perpetuals in the same account,
- trades across US and Asian hours,
- has enough size that a forced liquidation is materially damaging.

This is a concrete segment. It is not "all traders".

## Product value

- **For the trader:** an agent that watches the interaction continuously, quantifies the risk
  under stated assumptions, and executes a bounded protective action instead of waking them up.
- **For Bitget:** fewer forced liquidations on accounts that were solvent on one leg and
  underwater on the interaction, and a demonstration that the UTA cross-asset design is safe to
  use at size.
- **After the hackathon:** the same governor generalises to any cross-asset book where one leg
  prices on a different clock than the other.
