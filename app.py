import os
from flask import Flask, render_template, request, flash, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from binance.client import Client
from dotenv import load_dotenv

# 读取 .env 文件（最稳方式）
load_dotenv()

app = Flask(__name__)
app.secret_key = 'super-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
db = SQLAlchemy(app)

class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20))
    side = db.Column(db.String(10))
    price = db.Column(db.Float)
    qty = db.Column(db.Float)
    quote_qty = db.Column(db.Float)
    fee = db.Column(db.Float)
    fee_asset = db.Column(db.String(10))
    time = db.Column(db.DateTime)

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
    trades = Trade.query.order_by(Trade.time.desc()).all()
    return render_template('index.html', trades=trades)

@app.route('/sync', methods=['GET', 'POST'])
def sync():
    if request.method == 'POST':
        client = get_client()
        if not client:
            flash('API密钥读取失败！请检查 .env 文件', 'danger')
        else:
            try:
                start_str = request.form.get('start_time')
                start_ts = None if not start_str else int(datetime.strptime(start_str, '%Y-%m-%d').timestamp() * 1000)
                raw = client.get_my_trades(limit=1000, startTime=start_ts)
                added = 0
                for t in raw:
                    if not Trade.query.get(t['orderId']):
                        trade = Trade(id=t['orderId'], symbol=t['symbol'], side='BUY' if t['isBuyer'] else 'SELL',
                                    price=float(t['price']), qty=float(t['qty']), quote_qty=float(t['quoteQty']),
                                    fee=float(t['commission']), fee_asset=t['commissionAsset'],
                                    time=datetime.fromtimestamp(t['time']/1000))
                        db.session.add(trade)
                        added += 1
                db.session.commit()
                flash(f'同步成功！新增 {added} 笔交易', 'success')
            except Exception as e:
                flash(f'同步失败：{str(e)}', 'danger')
    return render_template('sync.html')

@app.route('/stats')
def stats():
    trades = Trade.query.all()
    total_fee = sum(t.fee for t in trades)
    initial = float(os.getenv('INITIAL_CAPITAL', 10000))
    loss = round(total_fee / initial * 100, 4) if initial else 0
    return render_template('stats.html', total_fee=total_fee, loss=loss, count=len(trades), initial=initial)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
