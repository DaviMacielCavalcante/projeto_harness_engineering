# Padrões de Projeto

Padrões de projeto são nomes compartilhados para soluções recorrentes de design.
Eles ajudam a equipe a comunicar intenção e reduzir acoplamento quando usados
com moderação.

## Strategy

Strategy encapsula uma família de algoritmos atrás de uma interface comum. O
cliente escolhe ou recebe a estratégia em tempo de execução, o que facilita
trocar comportamento sem reescrever a classe principal.

## Adapter

Adapter traduz uma interface existente para outra interface esperada pelo
cliente. É útil quando uma biblioteca externa não segue o contrato interno do
sistema.

## Factory

Factory centraliza regras de criação de objetos. Isso reduz duplicação quando
existem múltiplas implementações ou parâmetros de construção complexos.
