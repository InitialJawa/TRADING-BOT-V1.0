//+------------------------------------------------------------------+
//|                                               xauusd_all.mq5      |
//| All XAUUSD strategies in one EA. Select via Strategy param.      |
//+------------------------------------------------------------------+
#property copyright "Trading Bot"
#property version   "1.00"
#property description "XAUUSD All Strategies: 1=A(D1) 2=B(H4) 3=C(H4) 4=D(H1) 5=E(M15) 6=F(M15) 7=G(M15) 8=H(H1)"

input int      Strategy       = 4;        // 1=A 2=B 3=C 4=D 5=E 6=F 7=G 8=H
input double   RiskPct        = 0.5;
input double   ATR_SL_Mult    = 0.0;      // 0 = use strategy default
input double   ATR_TP_Mult    = 0.0;
input double   ATR_TrailMult  = 0.0;
input int      MaxHoldBars    = 0;
input int      MaxSpreadPts   = 300;
input double   FixedLot       = 0.0;      // 0 = auto calc

int hEma5, hEma9, hEma10, hEma13, hEma20, hEma21, hEma30, hEma50, hSma30, hSma120, hSma200;
int hRsi14, hAtr10, hAtr14, hMacd;
int hPsar;

double ema5[], ema9[], ema10[], ema13[], ema20[], ema21[], ema30[], ema50[];
double sma30[], sma120[], sma200[];
double rsi14[], atr10[], atr14[];
double macd_main[], macd_sig[];
double psar[];
double close1, close2;
datetime lastBarTime = 0, lastTradeDay = 0;
int ticket = 0, barsHeld = 0, totalTrades = 0;
double balance = 0;

// Strategy-specific state
int confScore = 0;
int activeStrategy = 0;

//+------------------------------------------------------------------+
int OnInit() {
   activeStrategy = Strategy;
   balance = AccountInfoDouble(ACCOUNT_BALANCE);
   if (balance <= 0) balance = 1000;

   hSma30  = iMA(_Symbol, PERIOD_CURRENT, 30, 0, MODE_SMA, PRICE_CLOSE);
   hSma120 = iMA(_Symbol, PERIOD_CURRENT, 120, 0, MODE_SMA, PRICE_CLOSE);
   hSma200 = iMA(_Symbol, PERIOD_CURRENT, 200, 0, MODE_SMA, PRICE_CLOSE);
   hEma5   = iMA(_Symbol, PERIOD_CURRENT, 5, 0, MODE_EMA, PRICE_CLOSE);
   hEma9   = iMA(_Symbol, PERIOD_CURRENT, 9, 0, MODE_EMA, PRICE_CLOSE);
   hEma10  = iMA(_Symbol, PERIOD_CURRENT, 10, 0, MODE_EMA, PRICE_CLOSE);
   hEma13  = iMA(_Symbol, PERIOD_CURRENT, 13, 0, MODE_EMA, PRICE_CLOSE);
   hEma20  = iMA(_Symbol, PERIOD_CURRENT, 20, 0, MODE_EMA, PRICE_CLOSE);
   hEma21  = iMA(_Symbol, PERIOD_CURRENT, 21, 0, MODE_EMA, PRICE_CLOSE);
   hEma30  = iMA(_Symbol, PERIOD_CURRENT, 30, 0, MODE_EMA, PRICE_CLOSE);
   hEma50  = iMA(_Symbol, PERIOD_CURRENT, 50, 0, MODE_EMA, PRICE_CLOSE);
   hRsi14  = iRSI(_Symbol, PERIOD_CURRENT, 14, PRICE_CLOSE);
   hAtr10  = iATR(_Symbol, PERIOD_CURRENT, 10);
   hAtr14  = iATR(_Symbol, PERIOD_CURRENT, 14);
   hMacd   = iMACD(_Symbol, PERIOD_CURRENT, 12, 26, 9, PRICE_CLOSE);
   hPsar   = iSAR(_Symbol, PERIOD_CURRENT, 0.02, 0.2);

   if (hSma30 == INVALID_HANDLE || hSma120 == INVALID_HANDLE || hSma200 == INVALID_HANDLE ||
       hRsi14 == INVALID_HANDLE || hAtr14 == INVALID_HANDLE || hMacd == INVALID_HANDLE) {
      Print("Indicator creation failed");
      return INIT_FAILED;
   }

   ArraySetAsSeries(ema5, true); ArraySetAsSeries(ema9, true);
   ArraySetAsSeries(ema10, true); ArraySetAsSeries(ema13, true);
   ArraySetAsSeries(ema20, true); ArraySetAsSeries(ema21, true);
   ArraySetAsSeries(ema30, true); ArraySetAsSeries(ema50, true);
   ArraySetAsSeries(sma30, true); ArraySetAsSeries(sma120, true); ArraySetAsSeries(sma200, true);
   ArraySetAsSeries(rsi14, true); ArraySetAsSeries(atr10, true); ArraySetAsSeries(atr14, true);
   ArraySetAsSeries(macd_main, true); ArraySetAsSeries(macd_sig, true);
   ArraySetAsSeries(psar, true);

   Print("XAUUSD All EA started. Strategy=", activeStrategy, " Balance=", balance);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   IndicatorRelease(hEma5); IndicatorRelease(hEma9); IndicatorRelease(hEma10);
   IndicatorRelease(hEma13); IndicatorRelease(hEma20); IndicatorRelease(hEma21);
   IndicatorRelease(hEma30); IndicatorRelease(hEma50);
   IndicatorRelease(hSma30); IndicatorRelease(hSma120); IndicatorRelease(hSma200);
   IndicatorRelease(hRsi14); IndicatorRelease(hAtr10); IndicatorRelease(hAtr14);
   IndicatorRelease(hMacd); IndicatorRelease(hPsar);
}

//+------------------------------------------------------------------+
void OnTick() {
   datetime currBarTime = iTime(_Symbol, PERIOD_CURRENT, 0);
   if (currBarTime == lastBarTime) return;
   lastBarTime = currBarTime;

   if (PositionSelect(_Symbol)) {
      barsHeld++;
      CheckExit();
      return;
   }

   //--- 1 trade per day
   MqlDateTime dt;
   TimeToStruct(currBarTime, dt);
   int today = dt.year * 10000 + dt.mon * 100 + dt.day;
   if (today == lastTradeDay) return;

   //--- Update balance periodically
   if (totalTrades % 5 == 0)
      balance = AccountInfoDouble(ACCOUNT_BALANCE);

   //--- Read all indicators
   if (CopyBuffer(hRsi14, 0, 1, 2, rsi14) < 2) return;
   if (CopyBuffer(hAtr14, 0, 0, 2, atr14) < 2) return;
   if (CopyBuffer(hAtr10, 0, 0, 2, atr10) < 2) return;

   close1 = iClose(_Symbol, PERIOD_CURRENT, 1);
   close2 = iClose(_Symbol, PERIOD_CURRENT, 2);

   //--- Spread check
   if ((int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > MaxSpreadPts) return;

   //--- Strategy switch
   int signal = 0;
   double slMult = ATR_SL_Mult;
   double tpMult = ATR_TP_Mult;
   double trailMult = ATR_TrailMult;
   int maxHold = MaxHoldBars;

   switch (activeStrategy) {
      case 1: signal = Signal_A(slMult, tpMult, trailMult, maxHold); break;
      case 2: signal = Signal_B(slMult, tpMult, trailMult, maxHold); break;
      case 3: signal = Signal_C(slMult, tpMult, trailMult, maxHold); break;
      case 4: signal = Signal_D(slMult, tpMult, trailMult, maxHold); break;
      case 5: signal = Signal_E(slMult, tpMult, trailMult, maxHold); break;
      case 6: signal = Signal_F(slMult, tpMult, trailMult, maxHold); break;
      case 7: signal = Signal_G(slMult, tpMult, trailMult, maxHold); break;
      case 8: signal = Signal_H(slMult, tpMult, trailMult, maxHold); break;
   }

   if (signal == 0) return;

   //--- Execute trade
   double lot = CalcLot();
   double price = (signal == 1) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double atr = atr14[0] > 0 ? atr14[0] : atr10[0];

   if (slMult <= 0) slMult = GetDefaultSLMult();
   if (tpMult <= 0) tpMult = GetDefaultTPMult();

   double sl, tp;
   if (signal == 1) {
      sl = price - atr * slMult;
      tp = price + atr * tpMult;
   } else {
      sl = price + atr * slMult;
      tp = price - atr * tpMult;
   }

   OpenOrder(signal, lot, price, sl, tp);
}

//+------------------------------------------------------------------+
// STRATEGY A: D1 SMA30 Pullback LONG ONLY
//+------------------------------------------------------------------+
int Signal_A(double &slM, double &tpM, double &trM, int &mHold) {
   if (slM <= 0) slM = 2.0;
   if (tpM <= 0) tpM = 3.0;
   if (trM <= 0) trM = 0.5;
   if (mHold <= 0) mHold = 90;
   if (CopyBuffer(hSma30, 0, 1, 1, sma30) < 1) return 0;
   if (CopyBuffer(hSma120, 0, 1, 1, sma120) < 1) return 0;
   if (CopyBuffer(hSma200, 0, 1, 1, sma200) < 1) return 0;

   double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if (price <= sma200[0]) return 0;      // Must be above SMA200 (bull market)
   if (rsi14[0] >= 45) return 0;          // RSI < 45 (not overbought on pullback)

   // Check if price is near SMA30 (pullback), within 0.5%
   double buf = sma30[0] * 0.005;
   if (close1 < sma30[0] - buf) return 0; // Too far below SMA30
   if (close1 > sma30[0] + buf) return 0; // Too far above SMA30

   return 1; // BUY only
}

//+------------------------------------------------------------------+
// STRATEGY B: H4 EMA10/30 Cross
//+------------------------------------------------------------------+
int Signal_B(double &slM, double &tpM, double &trM, int &mHold) {
   if (slM <= 0) slM = 1.5;
   if (tpM <= 0) tpM = 3.0;
   if (trM <= 0) trM = 0.5;
   if (mHold <= 0) mHold = 40;
   if (CopyBuffer(hEma10, 0, 1, 1, ema10) < 1) return 0;
   if (CopyBuffer(hEma30, 0, 1, 1, ema30) < 1) return 0;

   double vol = (double)iVolume(_Symbol, PERIOD_CURRENT, 1);
   double volMA = 0;
   for (int vi = 1; vi <= 20; vi++) volMA += (double)iVolume(_Symbol, PERIOD_CURRENT, vi);
   volMA /= 20.0;
   if (vol < volMA * 1.2) return 0;

   if (ema10[0] > ema30[0] && rsi14[0] >= 20 && rsi14[0] <= 80 && ema10[1] <= ema30[1]) return 1;
   if (ema10[0] < ema30[0] && rsi14[0] >= 20 && rsi14[0] <= 80 && ema10[1] >= ema30[1]) return -1;
   return 0;
}

//+------------------------------------------------------------------+
// STRATEGY C: H4 PSAR Flip
//+------------------------------------------------------------------+
int Signal_C(double &slM, double &tpM, double &trM, int &mHold) {
   if (slM <= 0) slM = 2.5;
   if (tpM <= 0) tpM = 4.0;
   if (trM <= 0) trM = 0.5;
   if (mHold <= 0) mHold = 50;
   if (CopyBuffer(hPsar, 0, 1, 2, psar) < 2) return 0;
   if (CopyBuffer(hEma20, 0, 1, 1, ema20) < 1) return 0;

   double vol = (double)iVolume(_Symbol, PERIOD_CURRENT, 1);
   double volMA = 0;
   for (int vi = 1; vi <= 20; vi++) volMA += (double)iVolume(_Symbol, PERIOD_CURRENT, vi);
   volMA /= 20.0;
   if (vol < volMA * 0.8) return 0;

   // PSAR flip BUY: prev bar below PSAR, current above PSAR
   if (close2 <= psar[1] && close1 > psar[0] && close1 > ema20[0]) return 1;
   // PSAR flip SELL: prev bar above PSAR, current below PSAR
   if (close2 >= psar[1] && close1 < psar[0] && close1 < ema20[0]) return -1;
   return 0;
}

//+------------------------------------------------------------------+
// STRATEGY D: H1 Confluence (EMA9/21 + RSI + MACD)
//+------------------------------------------------------------------+
int Signal_D(double &slM, double &tpM, double &trM, int &mHold) {
   if (slM <= 0) slM = 2.0;
   if (tpM <= 0) tpM = 4.0;
   if (trM <= 0) trM = 1.0;
   if (mHold <= 0) mHold = 24;
   if (CopyBuffer(hEma9, 0, 1, 1, ema9) < 1) return 0;
   if (CopyBuffer(hEma21, 0, 1, 1, ema21) < 1) return 0;
   if (CopyBuffer(hMacd, 0, 1, 1, macd_main) < 1) return 0;
   if (CopyBuffer(hMacd, 1, 1, 1, macd_sig) < 1) return 0;
   if (CopyBuffer(hEma50, 0, 1, 1, ema50) < 1) return 0;
   if (CopyBuffer(hSma200, 0, 1, 1, sma200) < 1) return 0;

   double vol = (double)iVolume(_Symbol, PERIOD_CURRENT, 1);
   double volMA = 0;
   for (int vi = 1; vi <= 20; vi++) volMA += (double)iVolume(_Symbol, PERIOD_CURRENT, vi);
   volMA /= 20.0;
   if (vol < volMA * 1.1) return 0;

   double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   bool bull = ema9[0] > ema21[0] && macd_main[0] > macd_sig[0];
   bool bear = ema9[0] < ema21[0] && macd_main[0] < macd_sig[0];

   if (bull && price > ema50[0] && price > sma200[0] && rsi14[0] >= 45 && rsi14[0] <= 75) return 1;
   if (bear && price < ema50[0] && price < sma200[0] && rsi14[0] >= 25 && rsi14[0] <= 55) return -1;
   return 0;
}

//+------------------------------------------------------------------+
// STRATEGY E: M15 NoFilter Momentum
//+------------------------------------------------------------------+
int Signal_E(double &slM, double &tpM, double &trM, int &mHold) {
   if (slM <= 0) slM = 0.7;
   if (tpM <= 0) tpM = 1.8;
   if (trM <= 0) trM = 0.4;
   if (mHold <= 0) mHold = 16;
   if (CopyBuffer(hEma5, 0, 1, 1, ema5) < 1) return 0;
   if (CopyBuffer(hEma13, 0, 1, 1, ema13) < 1) return 0;
   if (CopyBuffer(hMacd, 0, 1, 1, macd_main) < 1) return 0;
   if (CopyBuffer(hMacd, 1, 1, 1, macd_sig) < 1) return 0;

   double vol = (double)iVolume(_Symbol, PERIOD_CURRENT, 1);
   double volMA = 0;
   for (int vi = 1; vi <= 15; vi++) volMA += (double)iVolume(_Symbol, PERIOD_CURRENT, vi);
   volMA /= 15.0;
   if (vol < volMA * 0.7) return 0;

   if (ema5[0] > ema13[0] && rsi14[0] >= 35 && rsi14[0] <= 82 && macd_main[0] > macd_sig[0]) return 1;
   if (ema5[0] < ema13[0] && rsi14[0] >= 18 && rsi14[0] <= 65 && macd_main[0] < macd_sig[0]) return -1;
   return 0;
}

//+------------------------------------------------------------------+
// STRATEGY F: M15 Turbo Scalper
//+------------------------------------------------------------------+
int Signal_F(double &slM, double &tpM, double &trM, int &mHold) {
   if (slM <= 0) slM = 0.5;
   if (tpM <= 0) tpM = 2.2;
   if (trM <= 0) trM = 0.3;
   if (mHold <= 0) mHold = 20;
   if (CopyBuffer(hEma5, 0, 1, 1, ema5) < 1) return 0;
   if (CopyBuffer(hEma13, 0, 1, 1, ema13) < 1) return 0;

   double vol = (double)iVolume(_Symbol, PERIOD_CURRENT, 1);
   double volMA = 0;
   for (int vi = 1; vi <= 15; vi++) volMA += (double)iVolume(_Symbol, PERIOD_CURRENT, vi);
   volMA /= 15.0;
   if (vol < volMA * 0.7) return 0;

   if (ema5[0] > ema13[0] && rsi14[0] >= 30 && rsi14[0] <= 95) return 1;
   if (ema5[0] < ema13[0] && rsi14[0] >= 5 && rsi14[0] <= 70) return -1;
   return 0;
}

//+------------------------------------------------------------------+
// STRATEGY G: M15 Confidence Sizing
//+------------------------------------------------------------------+
int Signal_G(double &slM, double &tpM, double &trM, int &mHold) {
   if (slM <= 0) slM = 0.5;
   if (tpM <= 0) tpM = 2.2;
   if (trM <= 0) trM = 0.3;
   if (mHold <= 0) mHold = 20;
   if (CopyBuffer(hEma5, 0, 1, 1, ema5) < 1) return 0;
   if (CopyBuffer(hEma13, 0, 1, 1, ema13) < 1) return 0;

   double vol = (double)iVolume(_Symbol, PERIOD_CURRENT, 1);
   double volMA = 0;
   for (int vi = 1; vi <= 15; vi++) volMA += (double)iVolume(_Symbol, PERIOD_CURRENT, vi);
   volMA /= 15.0;

   //--- Base signal (same as F)
   int baseSig = 0;
   if (ema5[0] > ema13[0] && rsi14[0] >= 30 && rsi14[0] <= 95) baseSig = 1;
   if (ema5[0] < ema13[0] && rsi14[0] >= 5 && rsi14[0] <= 70) baseSig = -1;
   if (baseSig == 0) return 0;

   //--- Confidence scoring (0-6)
   confScore = 0;
   if (CopyBuffer(hEma9, 0, 1, 1, ema9) < 1) return baseSig;
   if (CopyBuffer(hEma21, 0, 1, 1, ema21) < 1) return baseSig;

   // H1 trend confluence (+2)
   if ((baseSig == 1 && ema9[0] > ema21[0]) || (baseSig == -1 && ema9[0] < ema21[0]))
      confScore += 2;

   // Volume spike (+1)
   if (vol > volMA * 1.2) confScore += 1;

   // RSI extreme (+1)
   if ((baseSig == 1 && rsi14[0] > 65) || (baseSig == -1 && rsi14[0] < 35))
      confScore += 1;

   // London session 07-14 UTC (+1)
   MqlDateTime dt;
   TimeToStruct(iTime(_Symbol, PERIOD_CURRENT, 0), dt);
   if (dt.hour >= 7 && dt.hour < 14) confScore += 1;

   return baseSig;
}

//+------------------------------------------------------------------+
// STRATEGY H: H1 Confidence Sizing
//+------------------------------------------------------------------+
int Signal_H(double &slM, double &tpM, double &trM, int &mHold) {
   if (slM <= 0) slM = 1.5;
   if (tpM <= 0) tpM = 3.0;
   if (trM <= 0) trM = 0.5;
   if (mHold <= 0) mHold = 24;
   if (CopyBuffer(hEma9, 0, 1, 1, ema9) < 1) return 0;
   if (CopyBuffer(hEma21, 0, 1, 1, ema21) < 1) return 0;

   double vol = (double)iVolume(_Symbol, PERIOD_CURRENT, 1);
   double volMA = 0;
   for (int vi = 1; vi <= 20; vi++) volMA += (double)iVolume(_Symbol, PERIOD_CURRENT, vi);
   volMA /= 20.0;
   if (vol < volMA * 0.8) return 0;

   double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   bool bull = ema9[0] > ema21[0];
   bool bear = ema9[0] < ema21[0];

   if (!bull && !bear) return 0;
   if (bull && (rsi14[0] < 40 || rsi14[0] > 80)) return 0;
   if (bear && (rsi14[0] < 20 || rsi14[0] > 60)) return 0;

   int baseSig = bull ? 1 : -1;

   //--- Confidence scoring
   confScore = 0;
   if (CopyBuffer(hEma50, 0, 1, 1, ema50) < 1) return baseSig;
   if (CopyBuffer(hSma200, 0, 1, 1, sma200) < 1) return baseSig;

   // H4 trend confluence (+2)
   double h4ema9 = iMA(_Symbol, PERIOD_H4, 9, 0, MODE_EMA, PRICE_CLOSE);
   double h4ema21 = iMA(_Symbol, PERIOD_H4, 21, 0, MODE_EMA, PRICE_CLOSE);
   double h4e9[1], h4e21[1];
   if (CopyBuffer(h4ema9, 0, 1, 1, h4e9) >= 1 && CopyBuffer(h4ema21, 0, 1, 1, h4e21) >= 1) {
      if ((bull && h4e9[0] > h4e21[0]) || (bear && h4e9[0] < h4e21[0]))
         confScore += 2;
   }
   IndicatorRelease(h4ema9); IndicatorRelease(h4ema21);

   // Volume spike (+1)
   if (vol > volMA * 1.2) confScore += 1;

   // RSI extreme (+1)
   if ((bull && rsi14[0] > 75) || (bear && rsi14[0] < 25))
      confScore += 1;

   // London session 07-14 UTC (+1)
   MqlDateTime dt;
   TimeToStruct(iTime(_Symbol, PERIOD_CURRENT, 0), dt);
   if (dt.hour >= 7 && dt.hour < 14) confScore += 1;

   // EMA200 side confirmation (+1)
   if ((bull && price > sma200[0]) || (bear && price < sma200[0]))
      confScore += 1;

   return baseSig;
}

//+------------------------------------------------------------------+
// EXIT CONDITIONS
//+------------------------------------------------------------------+
void CheckExit() {
   if (!PositionSelect(_Symbol)) return;

   int posType = (int)PositionGetInteger(POSITION_TYPE);
   double openP = PositionGetDouble(POSITION_PRICE_OPEN);
   double currSL = PositionGetDouble(POSITION_SL);
   double atr = atr14[0] > 0 ? atr14[0] : atr10[0];
   if (atr <= 0) return;

   //--- Max hold exit
   int hBars = GetMaxHold();
   if (barsHeld >= hBars) { ClosePosition("MAXHOLD"); return; }

   //--- EMA flip exit (for all except A)
   if (activeStrategy != 1) {
      if (CopyBuffer(hEma9, 0, 1, 1, ema9) < 1) return;
      if (CopyBuffer(hEma21, 0, 1, 1, ema21) < 1) return;
      if (posType == POSITION_TYPE_BUY && ema9[0] < ema21[0]) { ClosePosition("EMAFLIP"); return; }
      if (posType == POSITION_TYPE_SELL && ema9[0] > ema21[0]) { ClosePosition("EMAFLIP"); return; }
   }

   //--- For A: SMA120 exit
   if (activeStrategy == 1) {
      int posTypeA = (int)PositionGetInteger(POSITION_TYPE);
      if (CopyBuffer(hSma120, 0, 1, 1, sma120) < 1) return;
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if (bid < sma120[0]) { ClosePosition("SMA120"); return; }
   }

   //--- Trailing stop
   double trM = GetDefaultTrailMult();
   double td = atr * trM;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   if (posType == POSITION_TYPE_BUY) {
      if (bid - openP >= td) {
         double newSL = MathMax(currSL, bid - td * 0.5);
         if (newSL > currSL) ModifySL(newSL);
      }
   } else {
      if (openP - ask >= td) {
         double newSL = (currSL == 0) ? ask + td * 0.5 : MathMin(currSL, ask + td * 0.5);
         if (newSL < currSL || currSL == 0) ModifySL(newSL);
      }
   }
}

//+------------------------------------------------------------------+
double CalcLot() {
   if (FixedLot > 0) return FixedLot;
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   if (bal <= 0) bal = 1000;
   double baseLot = bal * (RiskPct / 100.0) * 0.04;  // 0.5% risk -> 0.02 lot @ $1000
   // Confidence sizing multiplier for G and H
   double mult = 1.0;
   if ((activeStrategy == 7 || activeStrategy == 8) && confScore >= 3)
      mult = 1.5;
   if ((activeStrategy == 7 || activeStrategy == 8) && confScore >= 5)
      mult = 2.0;

   double lot = baseLot * mult;
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double lotMin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double lotMax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   lot = MathMax(lotMin, MathRound(lot / lotStep) * lotStep);
   lot = MathMin(lot, lotMax);
   return lot;
}

//+------------------------------------------------------------------+
double GetDefaultSLMult() {
   switch (activeStrategy) {
      case 1: return 2.0; case 2: return 1.5; case 3: return 2.5;
      case 4: return 2.0; case 5: return 0.7; case 6: return 0.5;
      case 7: return 0.5; case 8: return 1.5;
   }
   return 2.0;
}
double GetDefaultTPMult() {
   switch (activeStrategy) {
      case 1: return 3.0; case 2: return 3.0; case 3: return 4.0;
      case 4: return 4.0; case 5: return 1.8; case 6: return 2.2;
      case 7: return 2.2; case 8: return 3.0;
   }
   return 3.0;
}
double GetDefaultTrailMult() {
   switch (activeStrategy) {
      case 1: return 0.5; case 2: return 0.5; case 3: return 0.5;
      case 4: return 1.0; case 5: return 0.4; case 6: return 0.3;
      case 7: return 0.3; case 8: return 0.5;
   }
   return 0.5;
}
int GetMaxHold() {
   switch (activeStrategy) {
      case 1: return 90;  case 2: return 40;  case 3: return 50;
      case 4: return 24;  case 5: return 16;  case 6: return 20;
      case 7: return 20;  case 8: return 24;
   }
   return 24;
}

//+------------------------------------------------------------------+
void OpenOrder(int type, double lot, double price, double sl, double tp) {
   MqlTradeRequest req = {};
   MqlTradeResult res = {};
   req.action   = TRADE_ACTION_DEAL;
   req.symbol   = _Symbol;
   req.volume   = lot;
   req.type     = (type == 1) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price    = price;
   req.sl       = sl;
   req.tp       = tp;
   req.deviation = 10;
   req.magic    = 30000 + activeStrategy;
   req.comment  = "S" + IntegerToString(activeStrategy);

   if (OrderSend(req, res)) {
      if (res.retcode == TRADE_RETCODE_DONE) {
         ticket = res.order;
         barsHeld = 0;
         totalTrades++;
         lastTradeDay = 0; // set at next bar
         MqlDateTime dt;
         TimeToStruct(iTime(_Symbol, PERIOD_CURRENT, 0), dt);
         lastTradeDay = dt.year * 10000 + dt.mon * 100 + dt.day;
         Print("OPEN S", activeStrategy, " ", (type == 1 ? "BUY" : "SELL"),
               " lot=", lot, " price=", price, " sl=", sl, " tp=", tp, " conf=", confScore);
      } else Print("ORDER FAIL: ", res.retcode);
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
   req.magic    = 30000 + activeStrategy;
   req.comment  = reason;
   if (OrderSend(req, res) && res.retcode == TRADE_RETCODE_DONE) {
      ticket = 0; barsHeld = 0;
      Print("CLOSE ", reason, " pnl=", pnl, " total=", totalTrades);
   }
}
//+------------------------------------------------------------------+
