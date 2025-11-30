import os
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-this-secret-key-2025'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)

class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    side = db.Column(db.String(10), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    quote_qty = db.Column(db.Float, nullable=False)
    fee = db.Column(db.Float, default=0.0)
    fee_asset = db.Column(db.String(10))
    is_maker = db.Column(db.Boolean, default=True)
    use_bnb = db.Column(db.Boolean, default=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.String(200))

with app.app_context():
    db.create_all()

def get_client():
    key = os.getenv('BINANCE_API_KEY')
    secret = os.getenv('BINANCE_SECRET_KEY')
    if not key or not secret:
        return None
    return Client(key, secret)

@app.route('/')
def index():
    trades = Trade.query.order_by(Trade.timestamp.desc()).limit(100).all()
    return render_template('index.html', trades=trades)

@app.route('/sync', methods=['GET', 'POST'])
def sync():
    msg = ""
    if request.method == 'POST':
        client = get_client()
        if not client:
            flash('API密钥未设置！', 'danger')
            return redirect('/sync')
        try:
            start_str = request.form.get('start_time', '')
            start_ts = None
            if start_str:
                start_ts = int(datetime.strptime(start_str, '%Y-%m-%d').timestamp() * 1000)
            
            all_trades = []
            symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']  # 可扩展
            for sym in symbols:
                try:
                    trades = client.get_my_trades(symbol=sym, startTime=start_ts, limit=1000)
                    all_trades.extend(trades)
                except:
                    continue
            
            added = 0
            for t in all_trades:
                if Trade.query.filter_by(id=t['orderId']).first():
                    continue
                new_trade = Trade(
                    id=t['orderId'],
                    symbol=t['symbol'],
                    side='BUY' if t['isBuyer'] else 'SELL',
                    price=float(t['price']),
                    quantity=float(t['qty']),
                    quote_qty=float(t['quoteQty']),
                    fee=float(t['commission']),
                    fee_asset=t['commissionAsset'],
                    timestamp=datetime.fromtimestamp(t['time']/1000)
                )
                db.session.add(new_trade)
                added += 1
            db.session.commit()
            flash(f'同步完成！新增 {added} 笔交易', 'success')
        except Exception as e:
            flash(f'同步失败：{str(e)}', 'danger')
    return render_template('sync.html')

@app.route('/stats')
def stats():
    trades = Trade.query.all()
    total_fee = sum(t.fee for t in trades)
    initial = float(os.getenv('INITIAL_CAPITAL', 10000))
    loss_rate = total_fee / initial * 100 if initial > 0 else 0
    
    # 简易盈亏计算
    cost = sum(t.quote_qty + t.fee for t in trades if t.side == 'BUY')
    income = sum(t.quote_qty - t.fee for t in trades if t.side == 'SELL')
    realized = income - cost
    
    return render_template('stats.html', 
        total_fee=round(total_fee,4),
        loss_rate=round(loss_rate,4),
        realized=round(realized,2),
        initial=initial,
        count=len(trades))

# 必须的模板路由
@app.route('/templates/<path:filename>')
def templates(filename):
    return render_template(filename)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
