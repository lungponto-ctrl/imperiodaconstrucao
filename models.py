from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def horario_local():
    """Retorna a data e hora atual do sistema local."""
    return datetime.now()


class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    cargo = db.Column(db.String(50), default='Vendedor')

    vendas = db.relationship('Venda', backref='vendedor', lazy=True)
    movimentacoes = db.relationship('MovimentacaoEstoque', backref='usuario', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Usuario {self.username}>'


class Categoria(db.Model):
    __tablename__ = 'categorias'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    produtos = db.relationship('Produto', backref='categoria', lazy=True)

    def __repr__(self):
        return f'<Categoria {self.nome}>'


class Produto(db.Model):
    __tablename__ = 'produtos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    codigo_barras = db.Column(db.String(50), unique=True, nullable=True)
    sku = db.Column(db.String(50), unique=True, nullable=True)

    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id'), nullable=True)
    unidade_base = db.Column(db.String(20), nullable=False, default='UN')

    quantidade_estoque = db.Column(db.Numeric(10, 3), nullable=False, default=0.000)
    estoque_minimo = db.Column(db.Numeric(10, 3), nullable=False, default=0.000)

    preco_custo = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    preco_venda_base = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)

    unidades_conversao = db.relationship('UnidadeConversao', backref='produto', cascade='all, delete-orphan', lazy=True)
    movimentacoes = db.relationship('MovimentacaoEstoque', backref='produto', cascade='all, delete-orphan', lazy=True)

    def __repr__(self):
        return f'<Produto {self.nome} Estoque: {self.quantidade_estoque} {self.unidade_base}>'


class UnidadeConversao(db.Model):
    __tablename__ = 'unidades_conversao'

    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=False)

    nome_unidade = db.Column(db.String(50), nullable=False)
    fator_conversao = db.Column(db.Numeric(10, 4), nullable=False)
    preco_venda = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)

    def __repr__(self):
        return f'<UnidadeConversao {self.nome_unidade} (Fator: {self.fator_conversao})>'


class MovimentacaoEstoque(db.Model):
    __tablename__ = 'movimentacoes_estoque'

    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=False)
    unidade_conversao_id = db.Column(db.Integer, db.ForeignKey('unidades_conversao.id'), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)

    tipo = db.Column(db.String(10), nullable=False)
    quantidade_informada = db.Column(db.Numeric(10, 3), nullable=False)
    fator_utilizado = db.Column(db.Numeric(10, 4), nullable=False, default=1.0)
    quantidade_base_calculada = db.Column(db.Numeric(10, 3), nullable=False)

    observacao = db.Column(db.String(255), nullable=True)
    data_movimentacao = db.Column(db.DateTime, default=horario_local)

    unidade_conversao = db.relationship('UnidadeConversao')


class Venda(db.Model):
    __tablename__ = 'vendas'

    id = db.Column(db.Integer, primary_key=True)
    cliente_nome = db.Column(db.String(150), nullable=False, default="Cliente Balcão")
    tipo = db.Column(db.String(20), nullable=False, default='ORCAMENTO')
    status = db.Column(db.String(20), nullable=False, default='ABERTO')

    valor_total = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    forma_pagamento = db.Column(db.String(50), nullable=True)

    # --- NOVOS CAMPOS DE ENTREGA ---
    possui_entrega = db.Column(db.Boolean, default=False)
    telefone_entrega = db.Column(db.String(30), nullable=True)
    endereco_entrega = db.Column(db.String(255), nullable=True)
    data_entrega = db.Column(db.String(20), nullable=True)
    valor_frete = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)

    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    data_criacao = db.Column(db.DateTime, default=horario_local)

    itens = db.relationship('ItemVenda', backref='venda', cascade='all, delete-orphan', lazy=True)

    def __repr__(self):
        return f'<Venda #{self.id} {self.tipo} R$ {self.valor_total}>'


class ItemVenda(db.Model):
    __tablename__ = 'itens_venda'

    id = db.Column(db.Integer, primary_key=True)
    venda_id = db.Column(db.Integer, db.ForeignKey('vendas.id'), nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=False)

    unidade_conversao_id = db.Column(db.Integer, db.ForeignKey('unidades_conversao.id'), nullable=True)

    quantidade = db.Column(db.Numeric(10, 3), nullable=False)
    preco_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

    produto = db.relationship('Produto')
    unidade_conversao = db.relationship('UnidadeConversao')

    def __repr__(self):
        return f'<ItemVenda Prod:{self.produto_id} Qtd:{self.quantidade}>'