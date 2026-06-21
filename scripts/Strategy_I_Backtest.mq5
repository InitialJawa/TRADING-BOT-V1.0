//+------------------------------------------------------------------+
//|                                           Strategy_I_Backtest.mq5 |
//|                                        Stage Analysis Enhanced V1 |
//+------------------------------------------------------------------+
#property copyright "Trading Bot"
#property version   "1.00"
#property description "Stage Analysis Enhanced - Strategy I"
#property description "Trades: BUY on Stage 2 (TREND+), SELL on Stage 4 (TREND-)"
#property description "SL check uses bar HIGH/LOW (all wicks covered)"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\AccountInfo.mqh>

CTrade Trade;
CPositionInfo PosInfo;
CAccountInfo AccInfo;

//+------------------------------------------------------------------+
//| INPUT PARAMETERS                                                 |
//+------------------------------------------------------------------+
input group "=== Strategy Parameters ==="
input double   InpRiskPct       = 0.5;         // Risk per trade (% of balance)
input double   InpATRSLMult     = 1.2;         // Hard SL: ATR multiplier
input double   InpATRTrailMult  = 0.8;         // Trail activation: ATR multiplier
input double   InpTrailSLMul    = 1.5;         // Trail SL offset multiplier
input double   InpStageThresh   = 0.0004;      // EMA21 slope threshold
input double   InpVolMult       = 0.8;         // Volume confirmation multiplier
input int      InpMagic         = 123456;      // Magic number

input group "=== Indicator Periods ==="
input int      InpEMAFast       = 9;
input int      InpEMAMedium     = 21;
input int      InpEMATrend      = 50;
input int      InpEMAMajor      = 200;
input int      InpRSIPeriod     = 14;
input int      InpATRPeriod     = 14;
input int      InpVolMAPeriod   = 20;

input group "=== Risk Control ==="
input int      InpStopOutDD     = 25;          // Stop trading if DD > this %

//+------------------------------------------------------------------+
//| INDICATOR HANDLES                                                |
//+------------------------------------------------------------------+
int hEMA9, hEMA21, hEMA50, hEMA200;
int hATR, hRSI, hVolMA, hBB;
int hEMA9_H4, hEMA21_H4;

//+------------------------------------------------------------------+
//| GLOBAL STATE                                                     |
//+------------------------------------------------------------------+
double gClose[], gEMA9[], gEMA21[], gEMA50[], gEMA200[];
double gATR[], gRSI[], gVolMA[];
double gBB_mid[], gBB_up[], gBB_lo[];

string gH4Trend = "NEUTRAL";
datetime gLastBarTime = 0;
datetime gLastH4Check = 0;
double gPeakBalance = 0;

//+------------------------------------------------------------------+
//| INIT                                                             |
//+------------------------------------------------------------------+
void OnInit()
{
   Trade.SetExpertMagicNumber(InpMagic);

   string sym = _Symbol;
   ENUM_TIMEFRAMES tf = PERIOD_CURRENT;

   hEMA9    = iMA(sym, tf, InpEMAFast,   0, MODE_EMA, PRICE_CLOSE);
   hEMA21   = iMA(sym, tf, InpEMAMedium,  0, MODE_EMA, PRICE_CLOSE);
   hEMA50   = iMA(sym, tf, InpEMATrend,   0, MODE_EMA, PRICE_CLOSE);
   hEMA200  = iMA(sym, tf, InpEMAMajor,   0, MODE_EMA, PRICE_CLOSE);
   hATR     = iATR(sym, tf, InpATRPeriod);
   hRSI     = iRSI(sym, tf, InpRSIPeriod, PRICE_CLOSE);
   hVolMA   = iMA(sym, tf, InpVolMAPeriod, 0, MODE_SMA, VOLUME_TICK);
   hBB      = iBands(sym, tf, 20, 0, 2, PRICE_CLOSE);
   hEMA9_H4  = iMA(sym, PERIOD_H4, 9,  0, MODE_EMA, PRICE_CLOSE);
   hEMA21_H4 = iMA(sym, PERIOD_H4, 21, 0, MODE_EMA, PRICE_CLOSE);

   if(hEMA9<0||hEMA21<0||hEMA50<0||hEMA200<0||hATR<0||hRSI<0||hVolMA<0||hBB<0)
   {
      Print("ERROR: Indicator handle creation failed on ", sym);
      ExpertRemove();
   }

   ArraySetAsSeries(gClose, true);  ArraySetAsSeries(gEMA9, true);
   ArraySetAsSeries(gEMA21, true);  ArraySetAsSeries(gEMA50, true);
   ArraySetAsSeries(gEMA200, true); ArraySetAsSeries(gATR, true);
   ArraySetAsSeries(gRSI, true);    ArraySetAsSeries(gVolMA, true);
   ArraySetAsSeries(gBB_mid, true); ArraySetAsSeries(gBB_up, true);
   ArraySetAsSeries(gBB_lo, true);
}

void OnDeinit(const int)
{
   IndicatorRelease(hEMA9);    IndicatorRelease(hEMA21);
   IndicatorRelease(hEMA50);   IndicatorRelease(hEMA200);
   IndicatorRelease(hATR);     IndicatorRelease(hRSI);
   IndicatorRelease(hVolMA);   IndicatorRelease(hBB);
   IndicatorRelease(hEMA9_H4); IndicatorRelease(hEMA21_H4);
}

//+------------------------------------------------------------------+
//| TICK                                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   datetime bt = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(bt == gLastBarTime) return;
   gLastBarTime = bt;

   UpdateH4Trend();
   if(!CopyBuffers()) return;

   double close   = gClose[1];
   double ema9    = gEMA9[1];
   double ema21   = gEMA21[1];
   double ema50   = gEMA50[1];
   double ema200  = gEMA200[1];
   double atr     = gATR[1];
   double rsi     = gRSI[1];
   long tvBuf[]; ArraySetAsSeries(tvBuf, true);
   CopyTickVolume(_Symbol, PERIOD_CURRENT, 0, 1, tvBuf);
   double vol = (double)tvBuf[0];
   double vol_ma  = gVolMA[1];
   double bbw     = (gBB_up[1] - gBB_lo[1]) / MathMax(gBB_mid[1], 1e-9);
   double bbw_ma  = GetBBWMA();
   bool squeeze   = (bbw < bbw_ma);
   double ema9_slope  = (gEMA9[6] > 0) ? (gEMA9[1] - gEMA9[6]) / gEMA9[6] * 100.0 : 0;
   double ema21_slope = (gEMA21[6] > 0) ? (gEMA21[1] - gEMA21[6]) / gEMA21[6] * 100.0 : 0;

   int stage = DetectStage(ema9, ema21, ema21_slope, close);
   string signal = GetSignal(stage, ema9, ema21, close, vol, vol_ma);
   int conf = CalcConfidence(ema9, ema21, close, ema200, rsi, vol, vol_ma, squeeze, Hour());
   double frac = (conf >= 5) ? 2.0 : (conf >= 3 ? 1.5 : 1.0);

   // Manage existing position
   if(PosInfo.Select(_Symbol))
   {
      ManagePosition(ema9, ema21, atr, stage, close);
      return;
   }

   // Stop-out on high DD
   double dd = GetDrawdown();
   if(dd > InpStopOutDD) return;

   // Open new
   if(signal != "HOLD")
   {
      double lots, sl;
      if(CalcLotSize(signal, atr, lots, sl))
         OpenTrade(signal, lots *= frac, sl, conf, frac);
   }
}

//+------------------------------------------------------------------+
//| STAGE DETECTION                                                  |
//+------------------------------------------------------------------+
int DetectStage(double e9, double e21, double e21s, double c)
{
   bool bull = (e9 > e21);
   bool pAbv = (c > e21);
   bool up   = (e21s > InpStageThresh);
   bool bear = (e9 < e21);
   bool pBlw = (c < e21);
   bool dn   = (e21s < -InpStageThresh);

   if(bull && pAbv && up) return 2;
   if(bear && pBlw && dn) return 4;
   if(bull && !up) return 3;
   return 1;
}

//+------------------------------------------------------------------+
//| SIGNAL                                                           |
//+------------------------------------------------------------------+
string GetSignal(int s, double e9, double e21, double c, double v, double vm)
{
   if(s == 1 || s == 3) return "HOLD";
   bool vOk = (v > vm * InpVolMult);
   if(s == 2 && e9 > e21 && c > e21 && vOk) return "BUY";
   if(s == 4 && e9 < e21 && c < e21 && vOk) return "SELL";
   return "HOLD";
}

//+------------------------------------------------------------------+
//| CONFIDENCE SCORE (0-7)                                           |
//+------------------------------------------------------------------+
int CalcConfidence(double e9, double e21, double c, double e200,
                   double rsi, double v, double vm, bool sqz, int hr)
{
   int s = 0;
   bool bull = (e9 > e21);
   if((bull && gH4Trend == "UP") || (!bull && gH4Trend == "DOWN")) s += 2;
   if(hr >= 7 && hr < 15) s += 1;
   if(v > vm * 1.2) s += 1;
   if(bull && rsi > 65) s += 1;
   if(!bull && rsi < 35) s += 1;
   if(sqz) s += 1;
   if((bull && c > e200) || (!bull && c < e200)) s += 1;
   return s;
}

//+------------------------------------------------------------------+
//| POSITION MANAGEMENT                                              |
//+------------------------------------------------------------------+
void ManagePosition(double e9, double e21, double atr, int stage, double close)
{
   ulong ticket = PosInfo.Ticket();
   int type = PosInfo.PositionType();
   double currSL = PosInfo.StopLoss();

   // Exit conditions
   if(stage == 3 || (type==POSITION_TYPE_BUY && e9<e21) || (type==POSITION_TYPE_SELL && e9>e21))
   {
      Trade.PositionClose(ticket);
      return;
   }

   // Trailing SL
   double td = atr * InpATRTrailMult;
   double dist = td * InpTrailSLMul;
   double newSL = (type == POSITION_TYPE_BUY) ? close - dist : close + dist;
   bool better = (type==POSITION_TYPE_BUY) ? (newSL > currSL) : (newSL < currSL || currSL==0);

   if(better)
      Trade.PositionModify(ticket, newSL, PosInfo.TakeProfit());
}

//+------------------------------------------------------------------+
//| RISK-BASED LOT SIZING (0.5% of balance)                         |
//+------------------------------------------------------------------+
bool CalcLotSize(string sig, double atr, double &lot, double &sl)
{
   double bal   = AccInfo.Balance();
   double tv    = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double ts    = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double vMin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vMax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double vStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   double price = (sig=="BUY") ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                               : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sd = atr * InpATRSLMult;
   sl = (sig=="BUY") ? price - sd : price + sd;

   double riskAmt = bal * InpRiskPct / 100.0;
   double slTicks = sd / MathMax(ts, 1e-9);
   double riskPerLot = slTicks * MathMax(tv, 1e-9);

   if(riskPerLot <= 0) return false;
   lot = MathFloor(riskAmt / riskPerLot / vStep) * vStep;
   lot = MathMax(vMin, MathMin(vMax, lot));
   return (lot >= vMin);
}

//+------------------------------------------------------------------+
//| OPEN TRADE                                                       |
//+------------------------------------------------------------------+
void OpenTrade(string sig, double lot, double sl, int conf, double frac)
{
   double price = (sig=="BUY") ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                               : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double vStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vMin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vMax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   lot = MathFloor(lot / vStep) * vStep;
   lot = MathMax(vMin, MathMin(vMax, lot));

   if(sig=="BUY") Trade.Buy(lot, _Symbol, 0, sl, 0);
   else           Trade.Sell(lot, _Symbol, 0, sl, 0);

   Print("OPEN ", _Symbol, " ", sig, " ", lot, " lots SL:", sl,
         " (conf:", conf, " x", frac, ")");
}

//+------------------------------------------------------------------+
//| H4 TREND UPDATE                                                  |
//+------------------------------------------------------------------+
void UpdateH4Trend()
{
   if(TimeCurrent() - gLastH4Check < 3600) return;
   gLastH4Check = TimeCurrent();

   double e9[], e21[];
   ArraySetAsSeries(e9, true); ArraySetAsSeries(e21, true);

   if(CopyBuffer(hEMA9_H4, 0, 0, 2, e9) < 2 || CopyBuffer(hEMA21_H4, 0, 0, 2, e21) < 2)
   { gH4Trend = "NEUTRAL"; return; }

   gH4Trend = (e9[0] > e21[0]) ? "UP" : ((e9[0] < e21[0]) ? "DOWN" : "NEUTRAL");
}

//+------------------------------------------------------------------+
//| COPY INDICATOR BUFFERS                                           |
//+------------------------------------------------------------------+
bool CopyBuffers()
{
   if(CopyClose(     _Symbol, PERIOD_CURRENT, 0, 250, gClose)  < 200) return false;
   if(CopyBuffer(hEMA9,   0, 0, 250, gEMA9)  < 200) return false;
   if(CopyBuffer(hEMA21,  0, 0, 250, gEMA21) < 200) return false;
   if(CopyBuffer(hEMA50,  0, 0, 250, gEMA50) < 200) return false;
   if(CopyBuffer(hEMA200, 0, 0, 250, gEMA200)< 200) return false;
   if(CopyBuffer(hATR,    0, 0, 250, gATR)   < 200) return false;
   if(CopyBuffer(hRSI,    0, 0, 250, gRSI)   < 200) return false;
   if(CopyBuffer(hVolMA,  0, 0, 250, gVolMA) < 200) return false;
   if(CopyBuffer(hBB,     0, 0, 250, gBB_mid)< 200) return false;
   if(CopyBuffer(hBB,     1, 0, 250, gBB_up) < 200) return false;
   if(CopyBuffer(hBB,     2, 0, 250, gBB_lo) < 200) return false;
   return true;
}

//+------------------------------------------------------------------+
//| BBW MA (20-period SMA of BB width)                               |
//+------------------------------------------------------------------+
double GetBBWMA()
{
   double s = 0;
   for(int i=0; i<20; i++)
      s += (gBB_up[i] - gBB_lo[i]) / MathMax(gBB_mid[i], 1e-9);
   return s / 20.0;
}

//+------------------------------------------------------------------+
//| CURRENT DRAWDOWN                                                 |
//+------------------------------------------------------------------+
double GetDrawdown()
{
   double bal = AccInfo.Balance();
   if(bal > gPeakBalance) gPeakBalance = bal;
   return (gPeakBalance - MathMax(bal, AccInfo.Equity())) / MathMax(gPeakBalance, 1) * 100.0;
}

//+------------------------------------------------------------------+
//| UTC HOUR                                                         |
//+------------------------------------------------------------------+
int Hour()
{
   MqlDateTime dt; TimeCurrent(dt); return dt.hour;
}
//+------------------------------------------------------------------+
