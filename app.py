from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime, date
from decimal import Decimal
import os
import shutil
from models import db, Categoria, Produto, UnidadeConversao, Venda, Usuario, MovimentacaoEstoque
from services import registrar_movimentacao, processar_venda

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///deposito.db'
app.config['SECRET_KEY'] = 'sua-chave-secreta-aqui'

db.init_app(app)

# Configuração do Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, faça login para acessar o sistema.'
login_manager.login_message_category = 'warning'


@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


# --- ROTINA DE BACKUP AUTOMÁTICO ---

def fazer_backup_automatico():
    """Gera um backup diário do banco SQLite de forma segura na pasta 'backups/'."""
    try:
        pasta_backup = 'backups'
        if not os.path.exists(pasta_backup):
            os.makedirs(pasta_backup)

        hoje = datetime.now().strftime('%Y-%m-%d')
        nome_arquivo_backup = os.path.join(pasta_backup, f'deposito_backup_{hoje}.db')

        # Localiza o arquivo de banco de dados atual
        caminho_banco = 'instance/deposito.db' if os.path.exists('instance/deposito.db') else 'deposito.db'

        if os.path.exists(caminho_banco):
            # Cria o backup apenas se ainda não existir um arquivo para o dia de hoje
            if not os.path.exists(nome_arquivo_backup):
                shutil.copy(caminho_banco, nome_arquivo_backup)
                print(f">>> [BACKUP] Cópia de segurança criada com sucesso: {nome_arquivo_backup}")
    except Exception as e:
        print(f">>> [BACKUP] Erro ao realizar backup automático: {str(e)}")


# --- ROTAS DE AUTENTICAÇÃO E USUÁRIOS ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        usuario = Usuario.query.filter_by(username=username).first()

        if usuario and usuario.check_password(password):
            login_user(usuario)
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha inválidos.', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sessão encerrada com sucesso.', 'info')
    return redirect(url_for('login'))


@app.route('/usuarios')
@login_required
def listar_usuarios():
    usuarios = Usuario.query.all()
    return render_template('listar_usuarios.html', usuarios=usuarios)


@app.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
def cadastrar_usuario():
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            username = request.form.get('username')
            password = request.form.get('password')
            cargo = request.form.get('cargo', 'Vendedor')

            if Usuario.query.filter_by(username=username).first():
                flash('Este nome de usuário já está em uso.', 'danger')
                return redirect(url_for('cadastrar_usuario'))

            novo_u = Usuario(nome=nome, username=username, cargo=cargo)
            novo_u.set_password(password)

            db.session.add(novo_u)
            db.session.commit()
            flash('Vendedor cadastrado com sucesso!', 'success')
            return redirect(url_for('listar_usuarios'))
        except Exception as e:
            db.session.rollback()
            return f"Erro ao cadastrar usuário: {str(e)}", 400

    return render_template('cadastrar_usuario.html')


# --- ROTAS DE EDIÇÃO E EXCLUSÃO DE USUÁRIOS ---

@app.route('/usuarios/<int:usuario_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_usuario(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    if request.method == 'POST':
        try:
            usuario.nome = request.form.get('nome')
            usuario.username = request.form.get('username')
            usuario.cargo = request.form.get('cargo', 'Vendedor')

            # Atualiza a senha apenas se o usuário preencheu o campo
            nova_senha = request.form.get('password')
            if nova_senha:
                usuario.set_password(nova_senha)

            db.session.commit()
            flash('Usuário atualizado com sucesso!', 'success')
            return redirect(url_for('listar_usuarios'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar usuário: {str(e)}', 'danger')

    return render_template('editar_usuario.html', usuario=usuario)


@app.route('/usuarios/<int:usuario_id>/excluir', methods=['POST'])
@login_required
def excluir_usuario(usuario_id):
    if current_user.id == usuario_id:
        flash('Você não pode excluir seu próprio usuário enquanto está logado.', 'danger')
        return redirect(url_for('listar_usuarios'))

    try:
        usuario = Usuario.query.get_or_404(usuario_id)
        db.session.delete(usuario)
        db.session.commit()
        flash('Usuário excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir usuário: {str(e)}', 'danger')
    return redirect(url_for('listar_usuarios'))


# --- ROTA DE DESBLOQUEIO POR INATIVIDADE ---

@app.route('/api/desbloquear', methods=['POST'])
@login_required
def desbloquear():
    try:
        dados = request.get_json() or request.form
        senha = dados.get('senha')

        if current_user.check_password(senha):
            return jsonify({'status': 'sucesso'}), 200
        else:
            return jsonify({'status': 'erro', 'mensagem': 'Senha incorreta.'}), 400
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500


# --- ROTAS DO SISTEMA (PROTEGIDAS) ---

@app.route('/')
@login_required
def index():
    produtos = Produto.query.all()
    return render_template('listar_produtos.html', produtos=produtos)


@app.route('/produtos/novo', methods=['GET', 'POST'])
@login_required
def cadastrar_produto():
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            codigo_barras = request.form.get('codigo_barras') or None
            sku = request.form.get('sku') or None
            categoria_id = request.form.get('categoria_id')
            unidade_base = request.form.get('unidade_base').upper()
            quantidade_estoque = float(request.form.get('quantidade_estoque') or 0)
            estoque_minimo = float(request.form.get('estoque_minimo') or 0)
            preco_custo = float(request.form.get('preco_custo') or 0)
            preco_venda_base = float(request.form.get('preco_venda_base') or 0)

            novo_produto = Produto(
                nome=nome,
                codigo_barras=codigo_barras,
                sku=sku,
                categoria_id=int(categoria_id) if categoria_id else None,
                unidade_base=unidade_base,
                quantidade_estoque=quantidade_estoque,
                estoque_minimo=estoque_minimo,
                preco_custo=preco_custo,
                preco_venda_base=preco_venda_base
            )

            db.session.add(novo_produto)
            db.session.flush()

            nomes_conversao = request.form.getlist('conversao_nome[]')
            fatores_conversao = request.form.getlist('conversao_fator[]')
            precos_conversao = request.form.getlist('conversao_preco[]')

            for nome_unidade, fator, preco in zip(nomes_conversao, fatores_conversao, precos_conversao):
                if nome_unidade and fator:
                    conversao = UnidadeConversao(
                        produto_id=novo_produto.id,
                        nome_unidade=nome_unidade,
                        fator_conversao=float(fator),
                        preco_venda=float(preco or 0)
                    )
                    db.session.add(conversao)

            db.session.commit()
            return redirect(url_for('index'))

        except Exception as e:
            db.session.rollback()
            return f"Erro ao cadastrar produto: {str(e)}", 400

    categorias = Categoria.query.order_by(Categoria.nome).all()
    return render_template('cadastrar_produto.html', categorias=categorias)


# --- ROTAS DE EDIÇÃO E EXCLUSÃO DE PRODUTOS ---

@app.route('/produtos/<int:produto_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_produto(produto_id):
    produto = Produto.query.get_or_404(produto_id)
    if request.method == 'POST':
        try:
            produto.nome = request.form.get('nome')
            produto.codigo_barras = request.form.get('codigo_barras') or None
            produto.sku = request.form.get('sku') or None
            categoria_id = request.form.get('categoria_id')
            produto.categoria_id = int(categoria_id) if categoria_id else None
            produto.unidade_base = request.form.get('unidade_base').upper()
            produto.estoque_minimo = float(request.form.get('estoque_minimo') or 0)
            produto.preco_custo = float(request.form.get('preco_custo') or 0)
            produto.preco_venda_base = float(request.form.get('preco_venda_base') or 0)

            db.session.commit()
            flash('Produto atualizado com sucesso!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            return f"Erro ao atualizar produto: {str(e)}", 400

    categorias = Categoria.query.order_by(Categoria.nome).all()
    return render_template('editar_produto.html', produto=produto, categorias=categorias)


@app.route('/produtos/<int:produto_id>/excluir', methods=['POST'])
@login_required
def excluir_produto(produto_id):
    try:
        produto = Produto.query.get_or_404(produto_id)
        UnidadeConversao.query.filter_by(produto_id=produto.id).delete()
        db.session.delete(produto)
        db.session.commit()
        flash('Produto excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir produto: {str(e)}', 'danger')
    return redirect(url_for('index'))


@app.route('/estoque/movimentar', methods=['POST'])
@login_required
def movimentar_estoque():
    try:
        produto_id = int(request.form.get('produto_id'))
        tipo = request.form.get('tipo').upper()
        quantidade = float(request.form.get('quantidade'))
        unidade_conversao_id = request.form.get('unidade_conversao_id')
        unidade_conversao_id = int(unidade_conversao_id) if unidade_conversao_id else None
        observacao = request.form.get('observacao')

        novo_saldo = registrar_movimentacao(
            produto_id=produto_id,
            tipo=tipo,
            quantidade=quantidade,
            unidade_conversao_id=unidade_conversao_id,
            observacao=observacao,
            usuario_id=current_user.id
        )

        return jsonify({
            'status': 'sucesso',
            'mensagem': 'Movimentação realizada com sucesso!',
            'novo_saldo_estoque': novo_saldo
        }), 200

    except ValueError as err:
        db.session.rollback()
        return jsonify({'status': 'erro', 'mensagem': str(err)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'erro', 'mensagem': f'Erro interno: {str(e)}'}), 500


@app.route('/vendas/nova', methods=['POST'])
@login_required
def criar_venda():
    try:
        dados = request.get_json()
        cliente_nome = dados.get('cliente_nome')
        tipo = dados.get('tipo', 'ORCAMENTO')
        forma_pagamento = dados.get('forma_pagamento')
        itens = dados.get('itens', [])
        dados_entrega = dados.get('dados_entrega', {})

        if not itens:
            return jsonify({'status': 'erro', 'mensagem': 'Nenhum item adicionado à venda.'}), 400

        venda_id = processar_venda(
            cliente_nome=cliente_nome,
            tipo_operacao=tipo,
            forma_pagamento=forma_pagamento,
            itens_carrinho=itens,
            usuario_id=current_user.id,
            dados_entrega=dados_entrega
        )

        return jsonify({
            'status': 'sucesso',
            'mensagem': f"{'Venda' if tipo == 'VENDA' else 'Orçamento'} registrado com sucesso!",
            'venda_id': venda_id
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500


@app.route('/pdv')
@login_required
def tela_pdv():
    produtos = Produto.query.all()
    return render_template('pdv.html', produtos=produtos)


@app.route('/vendas', methods=['GET'])
@login_required
def listar_vendas():
    vendas = Venda.query.order_by(Venda.data_criacao.desc()).all()
    return render_template('listar_vendas.html', vendas=vendas)


@app.route('/vendas/<int:venda_id>/detalhes', methods=['GET'])
@login_required
def detalhes_venda(venda_id):
    venda = Venda.query.get_or_404(venda_id)
    return render_template('_detalhes_venda.html', venda=venda)


@app.route('/vendas/<int:venda_id>/imprimir')
@login_required
def imprimir_venda(venda_id):
    venda = Venda.query.get_or_404(venda_id)
    return render_template('comprovante_venda.html', venda=venda)


# --- ROTA DE EXCLUSÃO DE VENDAS COM SENHA DE GERENTE E ESTORNO DE ESTOQUE ---

@app.route('/vendas/<int:venda_id>/excluir', methods=['POST'])
@login_required
def excluir_venda(venda_id):
    venda = Venda.query.get_or_404(venda_id)

    # Verifica se precisa de senha de gerente (se o usuário atual for Vendedor)
    if current_user.cargo != 'Gerente':
        senha_gerente = request.form.get('senha_gerente')
        gerentes = Usuario.query.filter_by(cargo='Gerente').all()

        autorizado = False
        for gerente in gerentes:
            if gerente.check_password(senha_gerente):
                autorizado = True
                break

        if not autorizado:
            flash('Senha de gerente inválida ou não autorizada para excluir esta venda.', 'danger')
            return redirect(url_for('listar_vendas'))

    try:
        # Transforma os itens em uma lista fixa para evitar problemas de concorrência no loop
        itens_venda = list(venda.itens)

        # 1. Estorna os produtos utilizando a função padrão do serviço oficial do sistema
        for item in itens_venda:
            registrar_movimentacao(
                produto_id=item.produto_id,
                tipo='ENTRADA',
                quantidade=float(item.quantidade),
                unidade_conversao_id=item.unidade_conversao_id,
                observacao=f'Estorno referente à exclusão da Venda #{venda.id}',
                usuario_id=current_user.id
            )

        # 2. Remove cada item explicitamente
        for item in itens_venda:
            db.session.delete(item)

        db.session.flush()

        # 3. Remove a venda principal
        db.session.delete(venda)
        db.session.commit()

        flash(f'Venda #{venda_id} excluída e estoque estornado com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        print(f">>> ERRO CRÍTICO AO EXCLUIR VENDA #{venda_id}: {str(e)}")
        flash(f'Erro ao excluir venda: {str(e)}', 'danger')

    return redirect(url_for('listar_vendas'))


@app.route('/relatorios')
@login_required
def relatorios():
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    busca = request.args.get('busca', '').strip()

    query = Venda.query.filter_by(tipo='VENDA')

    if data_inicio:
        query = query.filter(Venda.data_criacao >= datetime.strptime(f"{data_inicio} 00:00:00", "%Y-%m-%d %H:%M:%S"))
    if data_fim:
        query = query.filter(Venda.data_criacao <= datetime.strptime(f"{data_fim} 23:59:59", "%Y-%m-%d %H:%M:%S"))

    if busca:
        if busca.isdigit():
            query = query.filter((Venda.id == int(busca)) | (Venda.cliente_nome.ilike(f"%{busca}%")))
        else:
            query = query.filter(Venda.cliente_nome.ilike(f"%{busca}%"))

    vendas_filtradas = query.order_by(Venda.data_criacao.desc()).all()

    faturamento_total = sum(v.valor_total for v in vendas_filtradas)
    total_vendas = len(vendas_filtradas)
    total_orcamentos = Venda.query.filter_by(tipo='ORCAMENTO').count()

    hoje_inicio = datetime.combine(date.today(), datetime.min.time())
    hoje_fim = datetime.combine(date.today(), datetime.max.time())
    vendas_hoje = Venda.query.filter(
        Venda.tipo == 'VENDA',
        Venda.data_criacao >= hoje_inicio,
        Venda.data_criacao <= hoje_fim
    ).order_by(Venda.data_criacao.desc()).all()

    faturamento_hoje = sum(v.valor_total for v in vendas_hoje)

    return render_template('relatorios.html',
                           faturamento_total=faturamento_total,
                           total_vendas=total_vendas,
                           total_orcamentos=total_orcamentos,
                           vendas=vendas_filtradas,
                           vendas_hoje=vendas_hoje,
                           faturamento_hoje=faturamento_hoje,
                           data_inicio=data_inicio or '',
                           data_fim=data_fim or '',
                           busca=busca)


if __name__ == '__main__':
    with app.app_context():
        # Executa o backup automático do banco sempre que o sistema inicia
        fazer_backup_automatico()

        db.create_all()

        if Categoria.query.count() == 0:
            categorias_iniciais = [
                "Cimentos e Argamassas",
                "Areia, Brita e Pedras",
                "Tijolos e Blocos",
                "Pisos e Revestimentos",
                "Hidráulica / PVC",
                "Elétrica / Fios",
                "Tintas e Acessórios",
                "Ferramentas e Ferragens",
                "Diversos"
            ]
            for nome_cat in categorias_iniciais:
                db.session.add(Categoria(nome=nome_cat))
            db.session.commit()
            print(">>> Categorias padrão criadas com sucesso!")

        if not Usuario.query.first():
            admin = Usuario(nome="Administrador do Sistema", username="admin", cargo="Gerente")
            admin.set_password("123456")
            db.session.add(admin)
            db.session.commit()
            print(">>> Usuário administrador padrão criado: admin / 123456")

    app.run(debug=True)