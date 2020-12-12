# Standard library imports...
from datetime import datetime
import logging
import random

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import exc, Table, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship

# Local imports...
from .constants import WORD_LIST_PATH


logger = logging.getLogger(__name__)

db = SQLAlchemy()
session = db.session


def random_readable_string(length=3, wordlist=WORD_LIST_PATH):
    with open(wordlist) as f:
        lines = f.read().splitlines()
        string = ''
        for _ in range(length):
            string += random.choice(lines).title()
    return string


association_table = Table('association', db.Model.metadata,
                          Column('ips', String, ForeignKey('ips.address'), primary_key=True),
                          Column('tokens', Integer, ForeignKey('tokens.name'), primary_key=True))


class IP(db.Model):
    __tablename__ = 'ips'
    id = Column(Integer, primary_key=True)
    address = Column(String(255))

    def __repr__(self):
        return self.address


class Token(db.Model):
    __tablename__ = 'tokens'
    name = Column(String(255), primary_key=True)
    expiration_date = Column(DateTime, nullable=True)
    max_usage = Column(Integer, default=1)
    used = Column(Integer, default=0)
    disabled = Column(Boolean, default=False)
    ips = relationship("IP",
                       secondary=association_table,
                       lazy='subquery',
                       backref=db.backref('pages', lazy=True))

    def __init__(self, **kwargs):
        super(Token, self).__init__(**kwargs)
        if not self.name:
            self.name = random_readable_string()
        if self.used is None:
            self.used = 0
        if self.max_usage is None:
            self.max_usage = False

    def __repr__(self):
        return self.name

    def toDict(self):
        _token = {
            'name': self.name,
            'used': self.used,
            'expiration_date': str(self.expiration_date) if self.expiration_date else None,
            'max_usage': self.max_usage,
            'ips': list(map(lambda x: x.address, self.ips)),
            'disabled': bool(self.disabled),
            'active': self.active()
        }
        return _token

    def active(self):
        expired = False
        if self.expiration_date:
            expired = self.expiration_date < datetime.now()
        used = self.max_usage != 0 and self.max_usage <= self.used

        return (not expired) and (not used) and (not self.disabled)

    def use(self, ip_address=False):
        if self.active():
            self.used += 1
            if ip_address:
                self.ips.append(IP(address=ip_address))
            return True
        return False

    def disable(self):
        if self.active():
            self.disabled = True
            return True
        return False


class Tokens():
    def __init__(self):
        self.tokens = {}

        self.load()

    def __repr__(self):
        result = ''
        for tokens_key in self.tokens:
            result += '%s, ' % tokens_key
        return result[:-2]

    def toList(self):
        _tokens = []
        for tokens_key in self.tokens:
            _tokens.append(self.tokens[tokens_key].toDict())
        return _tokens

    def load(self):
        logger.debug('loading tokens from ..')
        self.tokens = {}
        for token in Token.query.all():
            logger.debug(token)
            self.tokens[token.name] = token

        logger.debug('token loaded!')

    def get_token(self, token_name):
        logger.debug('getting token by name: %s' % token_name)
        try:
            token = Token.query.filter_by(name=token_name).first()
        except KeyError:
            return False
        return token

    def active(self, token_name):
        logger.debug('checking if "%s" is active' % token_name)
        token = self.get_token(token_name)
        if token:
            return token.active()
        return False

    def use(self, token_name, ip_address=False):
        logger.debug('using token: %s' % token_name)
        token = self.get_token(token_name)
        if token:
            if token.use(ip_address):
                try:
                    session.commit()
                except exc.IntegrityError:
                    logger.warning("User already used this token before!")
                return True
        return False

    def disable(self, token_name):
        logger.debug('disabling token: %s' % token_name)
        token = self.get_token(token_name)
        if token:
            if token.disable():
                session.commit()
                return True
        return False

    def new(self, expiration_date=None, max_usage=False):
        logger.debug(('creating new token, with options: max_usage: {},' +
                     'expiration_dates: {}').format(max_usage, expiration_date))
        token = Token(expiration_date=expiration_date, max_usage=max_usage)
        self.tokens[token.name] = token
        session.add(token)
        session.commit()

        return token


tokens = None
ips = None
