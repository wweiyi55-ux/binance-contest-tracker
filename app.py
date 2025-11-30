import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException
from apscheduler.schedulers.background import BackgroundScheduler
import sys

load_dotenv()

# 修复版：用默认 template_folder，但显式设置 static_folder 和 root_path
dir_path = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(dir_path, 'static'), 
            template_folder=os.path.join(dir_path, 'templates'))
app.config['SECRET_KEY'] = 'change-this-secret-key-2025'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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
    print(f"Debug: API Key loaded: {bool(key)}")  # 调试打印
    if not key or not secret:
        return None
    testnet = os.getenv('TESTNET', 'False').lower() == 'true'
    return Client(key, secret, testnet=testnet)

@app.route('/')
def index():
    trades = Trade.query.order_by(Trade.timestamp.desc()).limit(100).all()
    return render_template('index.html', trades=trades)

@app.route('/sync', methods=['GET', 'POST'])
def sync():
    if request.method == 'POST':
        client = get_client()
        if not client:
            flash('API密钥未设置！请检查 Environment Variables。', 'danger')
            return render_template('sync.html')
        try:
            start_str = request.form.get('start_time', '')
            start_ts = None
            if start_str:
                start_ts = int(datetime.strptime(start_str, '%Y-%m-%d').timestamp() * 1000)
            trades = client.get_my_trades(limit=1000, startTime=start_ts)
            added = 0
            for t in trades:
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
        except BinanceAPIException as e:
            flash(f'币安API错误: {e.message}', 'danger')
        except Exception as e:
            flash(f'同步失败: {str(e)}', 'danger')
    return render_template('sync.html')

@app.route('/stats')
def stats():
    trades = Trade.query.all()
    total_fee = sum(t.fee for t in trades)
    initial = float(os.getenv('INITIAL_CAPITAL', 10000))
    loss_rate = round(total_fee / initial * 100, 4) if initial > 0 else 0
    cost = sum(t.quote_qty + t.fee for t in trades if t.side == 'BUY')
    income = sum(t.quote_qty - t.fee for t in trades if t.side == 'SELL')
    realized = round(income - cost, 2)
    return render_template('stats.html', 
        total_fee=total_fee,
        loss_rate=loss_rate,
        realized=realized,
        initial=initial,
        count=len(trades))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
