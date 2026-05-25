# Arquitetura hexagonal

[

![Márcio Krüger](https://miro.medium.com/v2/resize:fill:32:32/1*NKJNUa9sC9weNMUEeZtYMQ@2x.jpeg)





](https://medium.com/@marcio.kgr?source=post_page---byline--8958fb3e5507---------------------------------------)

[Márcio Krüger](https://medium.com/@marcio.kgr?source=post_page---byline--8958fb3e5507---------------------------------------)

Follow

5 min read

·

May 29, 2023

[

](https://medium.com/m/signin?actionUrl=https%3A%2F%2Fmedium.com%2F_%2Fvote%2Fp%2F8958fb3e5507&operation=register&redirect=https%3A%2F%2Fmedium.com%2F%40marcio.kgr%2Farquitetura-hexagonal-8958fb3e5507&user=M%C3%A1rcio+Kr%C3%BCger&userId=a286973f8d4c&source=---header_actions--8958fb3e5507---------------------clap_footer------------------)

31

[](https://medium.com/m/signin?actionUrl=https%3A%2F%2Fmedium.com%2F_%2Fbookmark%2Fp%2F8958fb3e5507&operation=register&redirect=https%3A%2F%2Fmedium.com%2F%40marcio.kgr%2Farquitetura-hexagonal-8958fb3e5507&source=---header_actions--8958fb3e5507---------------------bookmark_footer------------------)

Share

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/1*S12jj3_UyjH-5YKxUo5KiQ.png)

Arquitetura hexagonal arte por Márcio Krüger

Arquitetura hexagonal, ou arquitetura de portas e adaptadores (Ports and Adapters), deriva do trabalho de [Alistair Cockburn](https://alistair.cockburn.us/hexagonal-architecture/). É um padrão de arquitetura usado para projetar aplicativos de software. Com arquitetura hexagonal, colocamos nossas entradas e saídas no limite do nosso projeto. Isso nos permite isolar a lógica central do aplicativo do mundo exterior. Como nossas entradas e saídas estão na borda, podemos alternar seus manipuladores sem afetar nosso código principal. Em resumo é uma forma de organizar o código em camadas, cada qual com a sua responsabilidade, tendo como objetivo isolar totalmente a lógica da aplicação do mundo externo

A arquitetura hexagonal visa aumentar a capacidade de manutenção de nossas aplicações web para que nosso código exija menos trabalho em geral. A arquitetura hexagonal é representada por um hexágono. Cada um dos diferentes lados do hexágono representa maneiras diferentes que nosso sistema pode se comunicar com outros sistemas. Poderíamos nos comunicar usando solicitações HTTP, uma API REST, SQL, outras arquiteturas hexagonais, etc. Cada camada do hexágono é independente de outras camadas, para que possamos fazer alterações individuais sem afetar todo o sistema.

Vamos dar uma olhada em como uma arquitetura hexagonal pode ser:

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/0*Ujx7saeqJVjXvybC)

A camada de domínio da aplicação é representada como um hexágono. Dentro do hexágono, temos nossas entidades de domínio e os casos de uso que funcionam com elas. Como podemos ver, não há dependências de saída. Todas as nossas dependências apontam para o centro. O interior do hexágono, ou o domínio, não depende de nada além de si mesmo. Isso garante que a lógica de negócios seja separada das camadas técnicas. Ele também garante que podemos reutilizar a lógica do domínio. Se mudarmos nossa pilha, isso não terá impacto no código de domínio. O núcleo contém a lógica de negócios principal e as regras de negócios.

Fora do hexágono, vemos diferentes adaptadores que interagem com nossa aplicação. Adaptadores diferentes irão interagir com diferentes aspectos do aplicativo. Por exemplo, podemos ter um adaptador da Web que interage com um navegador da Web, alguns adaptadores que interagem com sistemas externos e um adaptador que interage com um banco de dados. Os adaptadores no lado esquerdo conduzem nosso aplicativo porque eles chamam nosso núcleo de aplicativo. Os adaptadores do lado direito são acionados pelo nosso aplicativo porque são chamados pelo nosso núcleo de aplicativo.

Os adaptadores são APIs externas do seu aplicativo ou clientes para outros sistemas. Os adaptadores usam portas para iniciar a interação com o aplicativo. Um controlador REST seria um exemplo de adaptador. O núcleo do aplicativo fornece portas para que ele possa se comunicar com os adaptadores. As portas nos permitem conectar os adaptadores ao domínio principal. Podemos pensar nos portos como pontos de entrada agnósticos.

> _Segundo Roger S. Pressman, em seu livro_ [_Engenharia de Software_](https://www.submarino.com.br/produto/159138/livro-engenharia-de-software?pfm_carac=Pressman&pfm_index=1&pfm_page=search&pfm_pos=grid&pfm_type=search_page+&sellerId=)_, a manutenção de software pode ser responsável por mais de 70% de todo o esforço despendido por uma organização de Software. E essa porcentagem continua aumentando à medida que mais Software é produzido._
> 
> _Para_ [_Martin Fowler_](https://www.saraiva.com.br/refatoracao-aperfeicoando-o-projeto-de-codigo-existente-3671050.html)_, um sistema mal projetado normalmente precisa de mais código para fazer as mesmas coisas, muitas vezes porque o mesmo código é replicado em diversos lugares diferentes. Assim, um aspecto importante na melhoria do projeto é a eliminação de código duplicado. A importância disto recai sobre futuras modificações no código._

## Princípio da Responsabilidade Única

A definição do Princípio da Responsabilidade Única é “um componente deve ter apenas uma razão para mudar”. Quando relacionado à arquitetura, isso significa que se um componente tem apenas um motivo para mudar, não precisamos nos preocupar com esse componente se mudarmos o software por qualquer outro motivo.

## Inversão de dependência

O princípio de inversão de dependência (DIP) nos permite inverter a direção de qualquer dependência dentro de nossa base de código. O problema é que só podemos inverter dependências quando temos controle de ambos os lados da dependência. Então, se tivermos uma dependência de uma biblioteca de terceiros, não podemos invertê-la porque não controlamos o código da biblioteca.

Vamos percorrer o princípio da inversão de dependência em ação. Digamos que queremos inverter a dependência entre nosso código de domínio e nosso código de persistência para que nosso código de persistência dependa do código de domínio. Usaremos a seguinte estrutura:

![](https://miro.medium.com/v2/resize:fit:633/0*orDN9yksQKgldzRA)

O problema que gera dependencia

O problema que gera dependencia

## Get Márcio Krüger’s stories in your inbox

Join Medium for free to get updates from this writer.

Subscribe

Subscribe

Remember me for faster sign in

Na estrutura acima, temos um serviço na camada de domínio que funciona com um repositório e uma entidade na camada de persistência. Podemos criar uma interface para o repositório na camada de domínio e deixar que o repositório na camada de persistência a implemente. Isso nos permite liberar nossa lógica de domínio de sua dependência do código de persistência. É assim que seria:

![](https://miro.medium.com/v2/resize:fit:560/0*tim8S3gRAIcv-0lb)

Inversão de dependência

## Isolar limites usando portas e adaptadores

Portas e adaptadores nos permitem executar nosso aplicativo em um modo totalmente isolado. A arquitetura hexagonal usa portas e adaptadores para ilustrar a comunicação entre o interior e o exterior. As portas são os limites da nossa aplicação. Existem dois tipos de portas: primária e secundária.

As portas primárias, ou portas de entrada, são os pontos de comunicação iniciais entre o mundo externo e o núcleo do aplicativo. As portas primárias são onde as solicitações chegam ao aplicativo. As portas secundárias, ou portas de saída, são usadas pelo núcleo do aplicativo para upstream de dados para serviços externos.

Os adaptadores servem como a implementação de nossas portas. Existem dois tipos de adaptadores: primário e secundário. Os adaptadores primários são implementações de portas primárias. Eles são independentes do núcleo do aplicativo. Adaptadores secundários são implementações de portas secundárias. Eles também são independentes do núcleo do aplicativo.

## Organizando meu projeto .NET

Lembrando que, isto é um exemplo que como pode ser organizado, e não uma regra. Ao final, vou disponibilizar o link do [github](https://github.com/marciokgr/hexagonal-architecture), de uma separação em .NET 7

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/0*DA-VUfJf4h2eVPN-)

Arquitetura hexagonal

-   **Application (Camada de Aplicação)**

É a camada responsável por se comunicar diretamente com o domínio e nela estão implementados: as classes dos serviços da aplicação, interfaces (ou contratos), Data Transfer Objects (DTO). E serve também para transformação do dados para a camada de domínio.

-   **Domain (Camada de domínio)**

É onde o DDD acontece, e nela estão: entidades, interfaces para serviços, classes dos serviços do domínio e validações.

-   **Infrastructure (Camada de infra estrutura)**

É camada que dá suporte a todas as demais camadas e pode ser dividida em: repositórios, mapeamento e persistência de dados.

## Considerações

Lembrando que o projeto de exemplo, não é uma regra e apenas um exemplo de separação. A ideia principal é deixar que as camadas de infra estrutura fiquem fáceis de serem alteradas sem afetar toda a aplicação, ou seja, baixo acoplamento.

## LINKS:

[marciokgr/hexagonal-architecture: hexagonal-architecture — Modelo projeto utilizando arquitetura hexagonal (github.com)](https://github.com/marciokgr/hexagonal-architecture)