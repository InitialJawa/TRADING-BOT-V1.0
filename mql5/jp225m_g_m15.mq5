//+------------------------------------------------------------------+
//|                                      jp225m_g_m15_confidence.mq5 |
//+------------------------------------------------------------------+
#property copyright "Trading Bot"
#property version   "2.00"
#property description "JP225m G M15 — SIMPLE: 0.5% risk, max 1 trade/day"

input double   RiskPct        = 0.5;   // % risk per trade
input double   ATR_SL_Mult    = 2.0;
input double   ATR_TP_Mult    = 5.0;
input double   ATR_Trail_Mult = 0.5;
input int      MaxHoldBars    = 48;
input bool     UseTrailing    = true;
input int      MinConfidence  = 4;     // stricter: 4+
input int      MaxSpreadPts   = 150;
input int      MaxLossStreak  = 2;     // skip after 2 losses

int hEma5, hEma13, hEma50, hRsi14, hAtr14;
int hBB_20_2;
int hEma9_H1, hEma21_H1;

double ema5[], ema13[], ema50[], rsi[], atr[];
double bb_up[5], bb_mid[5], bb_lo[5];
double ema9_h1[], ema21_h1[];

datetime lastBarTime = 0, lastTradeDay = 0;
int ticket = 0, barsHeld = 0;
bool trailActive = false;
int lossStreak = 0;
double lastTradeBalance = 0;

//+------------------------------------------------------------------+
int OnInit() {
   hEma5    = iMA(_Symbol, PERIOD_CURRENT, 5, 0, MODE_EMA, PRICE_CLOSE);
   hEma13   = iMA(_Symbol, PERIOD_CURRENT, 13, 0, MODE_EMA, PRICE_CLOSE);
   hEma50   = iMA(_Symbol, PERIOD_CURRENT, 50, 0, MODE_EMA, PRICE_CLOSE);
   hRsi14   = iRSI(_Symbol, PERIOD_CURRENT, 14, PRICE_CLOSE);
   hAtr14   = iATR(_Symbol, PERIOD_CURRENT, 14);
   hBB_20_2 = iBands(_Symbol, PERIOD_CURRENT, 20, 0, 2.0, PRICE_CLOSE);
   hEma9_H1  = iMA(_Symbol, PERIOD_H1, 9, 0, MODE_EMA, PRICE_CLOSE);
   hEma21_H1 = iMA(_Symbol, PERIOD_H1, 21, 0, MODE_EMA, PRICE_CLOSE);

   if (hEma5 == INVALID_HANDLE || hEma13 == INVALID_HANDLE || hRsi14 == INVALID_HANDLE ||
       hAtr14 == INVALID_HANDLE || hBB_20_2 == INVALID_HANDLE ||
       hEma9_H1 == INVALID_HANDLE || hEma21_H1 == INVALID_HANDLE) {
      Print("Indicator creation failed");
      return INIT_FAILED;
   }
   ArraySetAsSeries(ema5, true);  ArraySetAsSeries(ema13, true);
   ArraySetAsSeries(ema50, true); ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(atr, true);
   ArraySetAsSeries(bb_up, true); ArraySetAsSeries(bb_mid, true);
   ArraySetAsSeries(bb_lo, true);
   ArraySetAsSeries(ema9_h1, true); ArraySetAsSeries(ema21_h1, true);
   lastTradeBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   IndicatorRelease(hEma5);   IndicatorRelease(hEma13);  IndicatorRelease(hEma50);
   IndicatorRelease(hRsi14);  IndicatorRelease(hAtr14);
   IndicatorRelease(hBB_20_2);
   IndicatorRelease(hEma9_H1); IndicatorRelease(hEma21_H1);
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

   //--- Loss streak cooldown
   if (lossStreak >= MaxLossStreak) {
      static int skipDays = 0;
      skipDays++;
      if (skipDays < 5) return;   // skip 5 days
      lossStreak = 0; skipDays = 0;
      Print("Cooldown over");
   }

   if (CopyBuffer(hEma5, 0, 1, 1, ema5) < 1) return;
   if (CopyBuffer(hEma13, 0, 1, 1, ema13) < 1) return;
   if (CopyBuffer(hRsi14, 0, 1, 1, rsi) < 1) return;
   if (CopyBuffer(hAtr14, 0, 1, 1, atr) < 1) return;
   if (CopyBuffer(hBB_20_2, 0, 1, 5, bb_up) < 5) return;
   if (CopyBuffer(hBB_20_2, 1, 1, 5, bb_mid) < 5) return;
   if (CopyBuffer(hBB_20_2, 2, 1, 5, bb_lo) < 5) return;
   if (CopyBuffer(hEma9_H1, 0, 1, 1, ema9_h1) < 1) return;
   if (CopyBuffer(hEma21_H1, 0, 1, 1, ema21_h1) < 1) return;

   long tickVol = (long)iVolume(_Symbol, PERIOD_CURRENT, 1);
   double volMA = 0;
   for (int vi = 1; vi <= 15; vi++) volMA += (double)iVolume(_Symbol, PERIOD_CURRENT, vi);
   volMA /= 15.0;

   double bbw_now = (bb_up[0] - bb_lo[0]) / bb_mid[0];
   double bbw_prev = (bb_up[1] - bb_lo[1]) / bb_mid[1];
   bool squeeze = (bbw_now < bbw_prev);
   bool bullH1 = (ema9_h1[0] > ema21_h1[0]);
   bool bull = (ema5[0] > ema13[0]);

   TimeToStruct(iTime(_Symbol, PERIOD_CURRENT, 1), dt);
   int hourUTC = dt.hour;

   int conf = 0;
   if ((bull && bullH1) || (!bull && !bullH1)) conf += 2;
   if (squeeze) conf += 1;
   if (tickVol > volMA * 1.2) conf += 1;
   if (bull && rsi[0] > 65) conf += 1;
   if (!bull && rsi[0] < 35) conf += 1;
   if (hourUTC >= 7 && hourUTC < 15) conf += 1;

   static int barCount = 0;
   barCount++;
   if (barCount % 50 == 1) {
      PrintFormat("BAR> e5=%.2f e13=%.2f rsi=%.1f atr=%.2f conf=%d h1tr=%d lossStreak=%d",
         ema5[0], ema13[0], rsi[0], atr[0], conf, bullH1, lossStreak);
   }

   if (conf < MinConfidence) return;

   int spreadPts = (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if (spreadPts > MaxSpreadPts) return;

   //--- Fixed lot: $1000 -> 0.3 lot
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double lot = MathRound(balance / 1000.0 * 3) / 10.0;
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double lotMin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   lot = MathMax(lotMin, MathRound(lot / lotStep) * lotStep);
   lot = MathMin(lot, 2.0);

   bool volOk = (tickVol > volMA * 0.5);
   if (bull && rsi[0] >= 30 && rsi[0] <= 95 && volOk) {
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double sl = ask - atr[0] * ATR_SL_Mult;
      double tp = ask + atr[0] * ATR_TP_Mult;
      OpenOrder(ORDER_TYPE_BUY, lot, ask, sl, tp, conf);
      return;
   }

   if (!bull && rsi[0] >= 5 && rsi[0] <= 70 && volOk) {
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double sl = bid + atr[0] * ATR_SL_Mult;
      double tp = bid - atr[0] * ATR_TP_Mult;
      OpenOrder(ORDER_TYPE_SELL, lot, bid, sl, tp, conf);
   }
}

//+------------------------------------------------------------------+
void OpenOrder(int type, double lot, double price, double sl, double tp, int conf) {
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
   req.magic    = 22501;
   req.comment  = "G" + IntegerToString(conf);

   if (OrderSend(req, res)) {
      if (res.retcode == TRADE_RETCODE_DONE) {
         ticket = res.order;
         barsHeld = 0;
         trailActive = false;
         lastTradeBalance = AccountInfoDouble(ACCOUNT_BALANCE);
         Print("OPEN ", (type == ORDER_TYPE_BUY ? "BUY" : "SELL"),
               " lot=", lot, " price=", price, " sl=", sl, " tp=", tp, " conf=", conf);
      } else Print("ORDER FAIL: ", res.retcode);
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
   req.magic    = 22501;
   req.comment  = reason;
   if (OrderSend(req, res) && res.retcode == TRADE_RETCODE_DONE) {
      if (pnl < 0) lossStreak++;
      else lossStreak = 0;
      ticket = 0; barsHeld = 0; trailActive = false;
      Print("CLOSE ", reason, " pnl=", pnl, " lossStreak=", lossStreak);
   }
}
//+------------------------------------------------------------------+