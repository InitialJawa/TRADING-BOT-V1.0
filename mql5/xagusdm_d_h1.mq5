//+------------------------------------------------------------------+
//|                                     xagusdm_d_h1_confluence.mq5  |
//+------------------------------------------------------------------+
#property copyright "Trading Bot"
#property version   "2.00"
#property description "XAGUSDm D H1 — SIMPLE: 0.5% risk, max 1 trade/day"

input double   RiskPct        = 0.5;
input double   ATR_SL_Mult    = 2.5;
input double   ATR_TP_Mult    = 6.0;
input double   ATR_Trail_Mult = 0.6;
input int      MaxHoldBars    = 72;
input bool     UseTrailing    = true;
input int      MaxSpreadPts   = 250;
input int      MaxLossStreak  = 2;

int hEma9, hEma21, hEma200, hRsi14, hAtr14;
int hMacd;

double ema9[], ema21[], ema200[], rsi[], atr[];
double macd_main[], macd_sig[];

datetime lastBarTime = 0, lastTradeDay = 0;
int ticket = 0, barsHeld = 0;
bool trailActive = false;
int lossStreak = 0;

//+------------------------------------------------------------------+
int OnInit() {
   hEma9    = iMA(_Symbol, PERIOD_CURRENT, 9, 0, MODE_EMA, PRICE_CLOSE);
   hEma21   = iMA(_Symbol, PERIOD_CURRENT, 21, 0, MODE_EMA, PRICE_CLOSE);
   hEma200  = iMA(_Symbol, PERIOD_CURRENT, 200, 0, MODE_EMA, PRICE_CLOSE);
   hRsi14   = iRSI(_Symbol, PERIOD_CURRENT, 14, PRICE_CLOSE);
   hAtr14   = iATR(_Symbol, PERIOD_CURRENT, 14);
   hMacd    = iMACD(_Symbol, PERIOD_CURRENT, 12, 26, 9, PRICE_CLOSE);

   if (hEma9 == INVALID_HANDLE || hEma21 == INVALID_HANDLE || hEma200 == INVALID_HANDLE ||
       hRsi14 == INVALID_HANDLE || hAtr14 == INVALID_HANDLE || hMacd == INVALID_HANDLE) {
      Print("Indicator creation failed");
      return INIT_FAILED;
   }
   ArraySetAsSeries(ema9, true);  ArraySetAsSeries(ema21, true);
   ArraySetAsSeries(ema200, true); ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(atr, true);
   ArraySetAsSeries(macd_main, true); ArraySetAsSeries(macd_sig, true);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   IndicatorRelease(hEma9);   IndicatorRelease(hEma21);
   IndicatorRelease(hEma200); IndicatorRelease(hRsi14);
   IndicatorRelease(hAtr14);
   IndicatorRelease(hMacd);
}

//+------------------------------------------------------------------+
void OnTick() {
   datetime currBarTime = iTime(_Symbol, PERIOD_CURRENT, 0);
   if (currBarTime == lastBarTime) {
      ManageTrailing();
      return;
   }
   lastBarTime = currBarTime;
   barsHeld++;

   if (PositionSelect(_Symbol)) {
      if (barsHeld - 1 >= MaxHoldBars) ClosePosition("MAXHOLD");
      return;
   }

   //--- 1 trade per day
   MqlDateTime dt;
   TimeToStruct(currBarTime, dt);
   int today = dt.year * 10000 + dt.month * 100 + dt.day;
   if (today == lastTradeDay) return;
   lastTradeDay = today;

   if (lossStreak >= MaxLossStreak) {
      static int skipDays = 0;
      skipDays++;
      if (skipDays < 5) return;
      lossStreak = 0; skipDays = 0;
      Print("Cooldown over");
   }

   if (CopyBuffer(hEma9, 0, 1, 1, ema9) < 1) return;
   if (CopyBuffer(hEma21, 0, 1, 1, ema21) < 1) return;
   if (CopyBuffer(hEma200, 0, 1, 1, ema200) < 1) return;
   if (CopyBuffer(hRsi14, 0, 1, 1, rsi) < 1) return;
   if (CopyBuffer(hAtr14, 0, 1, 1, atr) < 1) return;
   if (CopyBuffer(hMacd, 0, 1, 1, macd_main) < 1) return;
   if (CopyBuffer(hMacd, 1, 1, 1, macd_sig) < 1) return;

   long tickVol = (long)iVolume(_Symbol, PERIOD_CURRENT, 1);
   double volMA = 0;
   for (int vi = 1; vi <= 20; vi++) volMA += (double)iVolume(_Symbol, PERIOD_CURRENT, vi);
   volMA /= 20.0;

   double priceC = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid    = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   bool bull   = (ema9[0] > ema21[0]);
   bool bear   = (ema9[0] < ema21[0]);
   bool above200 = (priceC > ema200[0]);

   bool rsiLong  = (rsi[0] >= 30 && rsi[0] <= 80);
   bool rsiShort = (rsi[0] >= 20 && rsi[0] <= 70);
   bool macdBull = (macd_main[0] > macd_sig[0]);
   bool macdBear = (macd_main[0] < macd_sig[0]);

   bool volOk = (tickVol > volMA * 0.3);
   int spreadPts = (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if (spreadPts > MaxSpreadPts) return;

   static int barDbg = 0;
   barDbg++;
   if (barDbg % 20 == 1) {
      PrintFormat("BAR> e9=%.4f e21=%.4f e200=%.4f rsi=%.1f vol=%d spread=%d lossStreak=%d",
         ema9[0], ema21[0], ema200[0], rsi[0], tickVol, spreadPts, lossStreak);
   }

   //--- Fixed lot: $1000 -> 0.2 lot (silver mini lebih kecil)
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double lot = MathRound(balance / 1000.0 * 2) / 10.0;
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double lotMin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   lot = MathMax(lotMin, MathRound(lot / lotStep) * lotStep);
   lot = MathMin(lot, 1.0);

   if (above200 && bull && rsiLong && macdBull && volOk) {
      double sl = priceC - atr[0] * ATR_SL_Mult;
      double tp = priceC + atr[0] * ATR_TP_Mult;
      OpenOrder(ORDER_TYPE_BUY, lot, priceC, sl, tp);
      return;
   }

   if (!above200 && bear && rsiShort && macdBear && volOk) {
      double sl = bid + atr[0] * ATR_SL_Mult;
      double tp = bid - atr[0] * ATR_TP_Mult;
      OpenOrder(ORDER_TYPE_SELL, lot, bid, sl, tp);
   }
}

//+------------------------------------------------------------------+
void OpenOrder(int type, double lot, double price, double sl, double tp) {
   MqlTradeRequest req = {};
   MqlTradeResult res = {};
   req.action   = TRADE_ACTION_DEAL;
   req.symbol   = _Symbol;
   req.volume   = lot;
   req.type     = type;
   req.price    = price;
   req.sl       = sl;
   req.tp       = tp;
   req.deviation = 10;
   req.magic    = 22502;
   req.comment  = "D";

   if (OrderSend(req, res)) {
      if (res.retcode == TRADE_RETCODE_DONE) {
         ticket = res.order;
         barsHeld = 0;
         trailActive = false;
         Print("OPEN ", (type == ORDER_TYPE_BUY ? "BUY" : "SELL"),
               " lot=", lot, " price=", price, " sl=", sl, " tp=", tp);
      } else Print("ORDER FAIL: ", res.retcode, " ", res.comment);
   }
}

//+------------------------------------------------------------------+
void ManageTrailing() {
   if (!UseTrailing || !PositionSelect(_Symbol)) return;
   if (CopyBuffer(hAtr14, 0, 0, 1, atr) < 1) return;
   if (atr[0] <= 0) return;

   double td = atr[0] * ATR_Trail_Mult;
   double currSL = PositionGetDouble(POSITION_SL);
   double openP = PositionGetDouble(POSITION_PRICE_OPEN);
   int pType = (int)PositionGetInteger(POSITION_TYPE);

   if (pType == POSITION_TYPE_BUY) {
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if (bid - openP >= td) trailActive = true;
      if (trailActive) {
         double newSL = bid - td * 0.5;
         if (newSL > currSL) ModifySL(newSL);
      }
   } else {
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      if (openP - ask >= td) trailActive = true;
      if (trailActive) {
         double newSL = ask + td * 0.5;
         if (newSL < currSL || currSL == 0) ModifySL(newSL);
      }
   }
}

//+------------------------------------------------------------------+
void ModifySL(double newSL) {
   MqlTradeRequest req = {};
   MqlTradeResult res = {};
   req.action   = TRADE_ACTION_SLTP;
   req.symbol   = _Symbol;
   req.position = PositionGetInteger(POSITION_TICKET);
   req.sl       = newSL;
   req.tp       = PositionGetDouble(POSITION_TP);
   if (OrderSend(req, res) && res.retcode == TRADE_RETCODE_DONE)
      Print("Trail: ", newSL);
}

//+------------------------------------------------------------------+
void ClosePosition(string reason) {
   if (!PositionSelect(_Symbol)) return;
   double pnl = PositionGetDouble(POSITION_PROFIT);
   MqlTradeRequest req = {};
   MqlTradeResult res = {};
   req.action   = TRADE_ACTION_DEAL;
   req.symbol   = _Symbol;
   req.volume   = PositionGetDouble(POSITION_VOLUME);
   req.type     = (int)PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   req.position = PositionGetInteger(POSITION_TICKET);
   req.price    = req.type == ORDER_TYPE_SELL ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                               : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   req.deviation = 10;
   req.magic    = 22502;
   req.comment  = reason;
   if (OrderSend(req, res) && res.retcode == TRADE_RETCODE_DONE) {
      if (pnl < 0) lossStreak++;
      else lossStreak = 0;
      ticket = 0; barsHeld = 0; trailActive = false;
      Print("CLOSE ", reason, " pnl=", pnl, " lossStreak=", lossStreak);
   }
}
//+------------------------------------------------------------------+