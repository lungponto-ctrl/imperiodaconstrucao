from models import db, Venda, ItemVenda, Produto, UnidadeConversao, MovimentacaoEstoque
from decimal import Decimal

def registrar_movimentacao(produto_id, tipo, quantidade, unidade_conversao_id=None, observacao=None, usuario_id=None):
    """
    Registra uma movimentação de estoque manual (ENTRADA ou SAIDA) pelo modal.
    """
    produto = Produto.query.get(produto_id)
    if not produto:
        raise ValueError(f"Produto ID {produto_id} não encontrado.")

    qtd = Decimal(str(quantidade))
    fator = Decimal('1.0000')

    if unidade_conversao_id:
        unidade = UnidadeConversao.query.get(unidade_conversao_id)
        if unidade:
            fator = Decimal(str(unidade.fator_conversao))

    qtd_base = qtd * fator

    if tipo.upper() == 'ENTRADA':
        produto.quantidade_estoque = Decimal(str(produto.quantidade_estoque)) + qtd_base
    elif tipo.upper() == 'SAIDA':
        produto.quantidade_estoque = Decimal(str(produto.quantidade_estoque)) - qtd_base
    else:
        raise ValueError("Tipo de movimentação inválido. Use 'ENTRADA' ou 'SAIDA'.")

    movimentacao = MovimentacaoEstoque(
        produto_id=produto.id,
        unidade_conversao_id=unidade_conversao_id,
        usuario_id=usuario_id,
        tipo=tipo.upper(),
        quantidade_informada=qtd,
        fator_utilizado=fator,
        quantidade_base_calculada=qtd_base,
        observacao=observacao
    )

    db.session.add(movimentacao)
    db.session.commit()
    return float(produto.quantidade_estoque)


def processar_venda(cliente_nome, tipo_operacao, forma_pagamento, itens_carrinho, usuario_id=None, dados_entrega=None):
    """
    Registra a Venda ou Orçamento, valida o estoque em caso de Venda Direta,
    adiciona frete se houver entrega, e realiza a baixa automática no estoque.
    """
    if not itens_carrinho:
        raise ValueError("O carrinho de compras está vazio.")

    valor_total_produtos = Decimal('0.00')
    itens_venda_objetos = []

    # 1. Validar e preparar os itens + Validar estoque se for VENDA
    for item in itens_carrinho:
        produto_id = item.get('produto_id')
        unidade_conversao_id = item.get('unidade_conversao_id')
        quantidade = Decimal(str(item.get('quantidade', 1)))

        produto = Produto.query.get(produto_id)
        if not produto:
            raise ValueError(f"Produto ID {produto_id} não encontrado.")

        # Determinar fator de conversão para cálculo correto da quantidade base
        fator = Decimal('1.0000')
        if unidade_conversao_id:
            unidade = UnidadeConversao.query.get(unidade_conversao_id)
            if unidade:
                fator = Decimal(str(unidade.fator_conversao))

        qtd_base_necessaria = quantidade * fator

        # Validação rígida de estoque para Venda Direta
        if tipo_operacao == 'VENDA':
            estoque_atual = Decimal(str(produto.quantidade_estoque or 0))
            if estoque_atual < qtd_base_necessaria:
                raise ValueError(
                    f"Estoque insuficiente para o produto '{produto.nome}'. "
                    f"Disponível: {estoque_atual} {produto.unidade_base}, Solicitado: {qtd_base_necessaria} {produto.unidade_base}."
                )

        preco_unitario = Decimal(str(produto.preco_venda_base))
        if unidade_conversao_id and 'unidade' in locals() and unidade:
            preco_unitario = Decimal(str(unidade.preco_venda))

        subtotal = quantidade * preco_unitario
        valor_total_produtos += subtotal

        item_venda = ItemVenda(
            produto_id=produto.id,
            unidade_conversao_id=unidade_conversao_id,
            quantidade=quantidade,
            preco_unitario=preco_unitario,
            subtotal=subtotal
        )
        itens_venda_objetos.append((item_venda, produto, quantidade, fator))

    # Tratar dados de entrega e frete
    possui_entrega = False
    telefone_entrega = None
    endereco_entrega = None
    data_entrega = None
    valor_frete = Decimal('0.00')

    if dados_entrega and dados_entrega.get('possui_entrega'):
        possui_entrega = True
        telefone_entrega = dados_entrega.get('telefone')
        endereco_entrega = dados_entrega.get('endereco')
        data_entrega = dados_entrega.get('data_entrega')
        valor_frete = Decimal(str(dados_entrega.get('valor_frete') or 0))

    valor_total_geral = valor_total_produtos + valor_frete

    # 2. Criar registro da Venda / Orçamento com os dados de entrega
    venda = Venda(
        cliente_nome=cliente_nome or "Cliente Balcão",
        tipo=tipo_operacao,
        status='CONCLUIDO' if tipo_operacao == 'VENDA' else 'ABERTO',
        forma_pagamento=forma_pagamento,
        valor_total=valor_total_geral,
        possui_entrega=possui_entrega,
        telefone_entrega=telefone_entrega,
        endereco_entrega=endereco_entrega,
        data_entrega=data_entrega,
        valor_frete=valor_frete,
        usuario_id=usuario_id
    )

    db.session.add(venda)
    db.session.flush()  # Gera o ID da venda

    # 3. Associar itens e processar estoque se for 'VENDA'
    for item_venda, produto, quantidade, fator in itens_venda_objetos:
        item_venda.venda_id = venda.id
        db.session.add(item_venda)

        if tipo_operacao == 'VENDA':
            qtd_base = quantidade * fator
            produto.quantidade_estoque = Decimal(str(produto.quantidade_estoque)) - qtd_base

            movimentacao = MovimentacaoEstoque(
                produto_id=produto.id,
                unidade_conversao_id=item_venda.unidade_conversao_id,
                usuario_id=usuario_id,
                tipo='SAIDA',
                quantidade_informada=quantidade,
                fator_utilizado=fator,
                quantidade_base_calculada=qtd_base,
                observacao=f"Venda Direta #{venda.id}"
            )
            db.session.add(movimentacao)

    db.session.commit()
    return venda.id