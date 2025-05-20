# models.py
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Tabla de asociación para favoritos
favorite_table = db.Table('favorite',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('name_id', db.Integer, db.ForeignKey('name.id'), primary_key=True)
)

# NUEVA Tabla de asociación para nombres pasados/descartados
passed_name_table = db.Table('passed_name',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('name_id', db.Integer, db.ForeignKey('name.id'), primary_key=True)
)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    
    favorites = db.relationship(
        'Name', 
        secondary=favorite_table, 
        backref=db.backref('favorited_by_users', lazy='dynamic') # Cambiado nombre de backref para claridad
    )
    
    # NUEVA relación para nombres pasados
    passed_names_rel = db.relationship(
        'Name',
        secondary=passed_name_table,
        backref=db.backref('passed_by_users', lazy='dynamic') # Cambiado nombre de backref para claridad
    )

    def __repr__(self):
        return f'<User {self.username}>'

class Name(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name_text = db.Column(db.String(100), nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    ranking = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return f'<Name {self.name_text} ({self.gender}) R:{self.ranking}>'