# Hexagonal Architecture: Arquiteturas de software

[

![Fabricio Gonçalves](https://miro.medium.com/v2/resize:fill:32:32/0*dDZIve2gKf6Fztdq.)





](https://medium.com/@espigah?source=post_page---byline--a4c55749a7eb---------------------------------------)

[Fabricio Gonçalves](https://medium.com/@espigah?source=post_page---byline--a4c55749a7eb---------------------------------------)

Follow

10 min read

·

Mar 1, 2021

[

](https://medium.com/m/signin?actionUrl=https%3A%2F%2Fmedium.com%2F_%2Fvote%2Fbemobi-tech%2Fa4c55749a7eb&operation=register&redirect=https%3A%2F%2Fmedium.com%2Fbemobi-tech%2Farquiteturas-de-software-a4c55749a7eb&user=Fabricio+Gon%C3%A7alves&userId=b906424fa3c7&source=---header_actions--a4c55749a7eb---------------------clap_footer------------------)

4

[](https://medium.com/m/signin?actionUrl=https%3A%2F%2Fmedium.com%2F_%2Fbookmark%2Fp%2Fa4c55749a7eb&operation=register&redirect=https%3A%2F%2Fmedium.com%2Fbemobi-tech%2Farquiteturas-de-software-a4c55749a7eb&source=---header_actions--a4c55749a7eb---------------------bookmark_footer------------------)

Share

![](https://miro.medium.com/v2/resize:fit:2469/1*DjKLj-y509W0OpLlZMCg-w.jpeg)

Em um momento no passado não muito distante, tentei ser simplista na forma de aplicar [Separation of Concerns (SoC)](https://en.wikipedia.org/wiki/Separation_of_concerns) no Frontend (o que apelidei de [Four Layers:](https://fabriciodezain.wordpress.com/2018/09/09/separation-of-concerns-soc-front-end-4-layers/) model, view, controller e “data”. Coincidentemente já existe uma proposta muito parecida que foi batizada de [Four Layer Architecture](http://wiki.c2.com/?FourLayerArchitecture=) ), e escrevi um bocado de como separar algumas coisas nesta camada.

Agora, neste artigo, a ideia vai ser mostrar algumas outras possibilidades para enriquecermos nosso repertório. Pra ser mais exato falarei de **Model-View-Controller (MVC)**, **Layered pattern**, **Boundary Control Entity (BCE)**, **Onion architecture**, **Hexagonal Architecture (Ports & Adapters)** e **Clean Architecture**, sem me aprofundar muito em cada uma delas, será apenas um pincelado sobre o que é, como normalmente um projeto usando uma dessa opções se parece e um bocado sobre as camadas de cada uma delas. Deixarei bastante referências para quem se interessar.

No final de tudo isso, irei propor um desafio, simples, para que possamos ajudar uns aos outros nessa parte tão complicada que é definir e evoluir uma arquitetura (acho até que é a real motivação do post =D ).

![](https://miro.medium.com/v2/resize:fit:275/0*5S5PibseGNK-c34c)

## Apertem os cintos

Com o advento e crescimento da adoção da Arquitetura de Microsserviços, também cresce a procura por padrões arquiteturais que podem ajudar na criação e implementação de serviços, mesmo que, em sua essência, tais padrões não se restringem exclusivamente a Microsserviços.

Lembrando que não existe bala de prata (nem mesmo a bala de prata foi feita pra superar todos os percalços, não é mesmo?) e toda escolha traz um custo, então acredito que vale conhecer várias ferramentas/abordagens, suas vantagens e custos e com base no conhecimento acumulado optar pelo possível melhor caminho naquele momento para solução do desafio apresentado.

> “Uma pessoa que imatura pensa que todas as suas escolhas geram ganhos… uma pessoa madura sabe que todas as escolhas tem perdas.” (Augusto Cury)

## Padrões arquiteturais

## Model-View-Controller

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/0*ICnkBrL2Rrohh9Cz.png)

O [MVC](https://pt.wikipedia.org/wiki/MVC), formulado na década de 1970, tenta melhorar a conexão entre as camadas de dados, lógica de negócio e interação com usuário.

Há algum tempo Model-View-Controller (mesmo que muitos usassem na real [Model-View-Presenter](https://pt.wikipedia.org/wiki/Model-view-presenter) sem saber) parecia ser predominante no mercado de trabalho, tinha muita coisa baseada nesse padrão.

**Algumas camadas importantes:**

-   **Model** — Ele é responsável pela leitura e escrita de dados, e também de suas validações;
-   **_View_** — Estando separado dos objetos Model, é responsável por usar as informações de que dispõe para produzir qualquer interface de apresentação que sua aplicação possa necessitar;
-   **_Controller_** — Lida com a solicitação do usuário. O _controller_ processa a solicitação e retorna a _view_ apropriada como uma resposta;

**Projeto:**

![](https://miro.medium.com/v2/resize:fit:342/0*KShpdj0gGvuZD8DI.jpg)

Camadas bem definidas, como: Models, Views e Controllers

**Referências**:

[https://www.lewagon.com/pt-BR/blog/o-que-e-padrao-mvc](https://www.lewagon.com/pt-BR/blog/o-que-e-padrao-mvc)  
[https://www.devmedia.com.br/introducao-ao-padrao-mvc/29308](https://www.devmedia.com.br/introducao-ao-padrao-mvc/29308)  
[https://www.treinaweb.com.br/blog/o-que-e-mvc/](https://www.treinaweb.com.br/blog/o-que-e-mvc/)

## Layered pattern

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/0*uAhInlkEyHvEzk2K.png)

Os padrões de arquitetura em camadas são padrões em que os componentes são organizados em camadas horizontais. Este é o método tradicional para projetar a maioria dos softwares e deve ser autônomo. Isso significa que todos os componentes estão interconectados, mas não dependem uns dos outros.

Não há um conjunto fixo de camadas que possa ser aplicado a todos os projetos, então você pode precisar pensar sobre que tipo de camadas funcionará para o projeto em questão.

**Algumas camadas importantes:**

-   **The presentation layer** : contém todas as categorias relacionadas à camada de apresentação;
-   **The business layer** : contém a lógica de negócios;
-   **The persistence layer** : é usada para lidar com funções como mapeamento relacional de objetos;
-   **The database layer** : é onde todos os dados são armazenados;

**Projeto:**

![](https://miro.medium.com/v2/resize:fit:251/1*vedLskjrYhIujsIz0m4hbw.jpeg)

**Referências**:

[https://priyalwalpita.medium.com/software-architecture-patterns-layered-architecture-a3b89b71a057](https://priyalwalpita.medium.com/software-architecture-patterns-layered-architecture-a3b89b71a057)  
[https://www.youtube.com/watch?v=V4RDMV0L-JM&ab\_channel=KavinKumar](https://www.youtube.com/watch?v=V4RDMV0L-JM&ab_channel=KavinKumar)  
[https://www.codeproject.com/Articles/654670/Layered-Application-Design-Pattern](https://www.codeproject.com/Articles/654670/Layered-Application-Design-Pattern)  
[http://engdashboard.blogspot.com/2017/09/software-architecture-patterns-layered.html](http://engdashboard.blogspot.com/2017/09/software-architecture-patterns-layered.html)

## Boundary Control Entity (BCE)

![](https://miro.medium.com/v2/resize:fit:380/0*HwBCklergCZQpsk5.gif)

A abordagem Boundary Control Entity encontra sua origem no [método OOSE dirigido por Ivar Jacobson publicado em 1992](https://archive.org/details/objectorientedso00jaco/page/130). Foi originalmente chamado de Entity-Interface-Control (EIC), mas rapidamente o termo “limite” substituiu “interface” para evitar a confusão potencial com a terminologia da linguagem de programação orientada a objetos.

Ao identificar os elementos para um cenário de comportamento do sistema, você pode alinhar cada elemento participante com uma das três perspectivas principais: **Entity** , **Control** ou **Boundary** . Um primeiro corte que cobre o comportamento do sistema necessário pode sempre ser montado com elementos dessas três perspectivas.

Este padrão é semelhante ao padrão MVC, mas o padrão ECB não é apenas apropriado para lidar com interfaces de usuário, e dá ao **_controller_** uma função ligeiramente diferente para desempenhar.

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/0*oCLhhmrw7hpBXAFM.jpg)

**Algumas camadas importantes:**

-   **Entity —** Entidades são objetos que representam dados do sistema: Cliente, Produto, Transação, Carrinho, etc;
-   **Boundary** — Limites são objetos que fazem interface com os atores do sistema: UserInterface, DataBaseGateway, ServerProxy, etc;
-   **Control —** Os controles são objetos que fazem a mediação entre limites e entidades;

**Projeto:**

![](https://miro.medium.com/v2/resize:fit:221/0*mqIeeL-cJm5Zsh-g.png)

**Referências**:

[https://stackoverflow.com/questions/26910974/model-view-controller-vs-boundary-control-entity](https://stackoverflow.com/questions/26910974/model-view-controller-vs-boundary-control-entity)  
[https://renatogbj.files.wordpress.com/2012/10/trabalho\_ps.pdf](https://renatogbj.files.wordpress.com/2012/10/trabalho_ps.pdf)  
[https://en.wikipedia.org/wiki/Entity-control-boundary](https://en.wikipedia.org/wiki/Entity-control-boundary)  
[http://www.utm.mx/~caff/doc/OpenUPWeb/openup/guidances/guidelines/entity\_control\_boundary\_pattern\_C4047897.html](http://www.utm.mx/~caff/doc/OpenUPWeb/openup/guidances/guidelines/entity_control_boundary_pattern_C4047897.html)  
[http://www.cs.sjsu.edu/~pearce/modules/patterns/enterprise/ecb/ecb.htm](http://www.cs.sjsu.edu/~pearce/modules/patterns/enterprise/ecb/ecb.htm)  
[http://www.utm.mx/~caff/doc/OpenUPWeb/openup/guidances/guidelines/entity\_control\_boundary\_pattern\_C4047897.html](http://www.utm.mx/~caff/doc/OpenUPWeb/openup/guidances/guidelines/entity_control_boundary_pattern_C4047897.html)

## Onion architecture

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/0*E9IZW35KFc4VvL-9.jpg)

A maioria das arquiteturas tradicionais levantam questões fundamentais de forte acoplamento e separação de interesses. A Onion Architecture foi apresentada por [Jeffrey Palermo](https://jeffreypalermo.com/author/jeffreypalermo/) para fornecer uma maneira melhor de construir aplicativos em perspectiva de melhor testabilidade, manutenção e confiabilidade.

A Onion Architecture é baseada no princípio de inversão de controle. A Onion Architecture é composta por várias camadas concêntricas que fazem interface entre si em direção ao núcleo que representa o domínio. A arquitetura não depende da camada de dados como nas arquiteturas multicamadas clássicas, mas dos modelos de domínio reais.

De acordo com a arquitetura tradicional, a camada de UI interage com a lógica de negócios e a lógica de negócios se comunica com a camada de dados, e todas as camadas estão misturadas e dependem fortemente umas das outras. Em arquiteturas de 3 e n camadas, nenhuma das camadas é independente; este fato levanta uma separação de preocupações. Esses sistemas são muito difíceis de entender e manter. A desvantagem dessa arquitetura tradicional é o acoplamento desnecessário.

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/0*BxbKk19Vn9vLG7xx.png)

**Algumas camadas importantes:**

-   **Application (orquestrador de domínio)** — Responsável por facilitar o acesso ao domínio;
-   **Domain (atores)** — Camada onde reside a lógica de negócio;
-   **Infrastructure (adaptador)** — Provê acesso aos sistemas externos, configurações etc;

**Projeto:**

![](https://miro.medium.com/v2/resize:fit:547/0*F0a7WKRhiyLAEabf.png)

**Referências**:

## Get Fabricio Gonçalves’s stories in your inbox

Join Medium for free to get updates from this writer.

Subscribe

Subscribe

Remember me for faster sign in

[https://www.infoq.com/br/articles/onion-architecture/](https://www.infoq.com/br/articles/onion-architecture/)  
[https://www.codeguru.com/csharp/csharp/cs\_misc/designtechniques/understanding-onion-architecture.html](https://www.codeguru.com/csharp/csharp/cs_misc/designtechniques/understanding-onion-architecture.html)  
[https://blog.thedigitalgroup.com/understanding-onion-architecture](https://blog.thedigitalgroup.com/understanding-onion-architecture)  
[https://jeffreypalermo.com/2008/07/the-onion-architecture-part-1/](https://jeffreypalermo.com/2008/07/the-onion-architecture-part-1/)

## Ports & Adapters ou Hexagonal Architecture

![](https://miro.medium.com/v2/resize:fit:313/0*HPSFDC56I_meQHDb.png)

A Hexagonal Architecture, também conhecido como Ports & Adapters, nome definido por [Alistair Cockburn](https://alistair.cockburn.us/coming-soon/) em seu artigo [Ports And Adapters Architecture](http://wiki.c2.com/?PortsAndAdaptersArchitecture=), onde, no contexto orientada a objetos, portas são as interfaces e adapters são as implementações.

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/0*R1uqM9EWhpEE4-YH.png)

Permitir que um aplicativo seja conduzido igualmente por usuários, programas, testes automatizados ou scripts em lote e seja desenvolvido e testado isoladamente de seus eventuais dispositivos de tempo de execução e bancos de dados.

A proposta era pensar numa arquitetura que houvesse uma separação bem definida, como: View Layer, Application Model, Domain Layer e Infrastructure Layer, ja que, não haveria muita diferença de se ter na aplicação uma comunicação com banco de dados e troca de dados via redes, com a interface do usuário, por exemplo.

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/0*5_-x8bZU7yHpjocY.png)

**Algumas camadas importantes:**

-   **Domain Objects** — Domínio de regras de negócios, os objetos de domínio são a força vital de um aplicativo. Os objetos de domínio podem conter estado e comportamento. Quanto mais próximo o comportamento estiver do estado, mais fácil será de entender, raciocinar e manter o código;
-   **Inbound gateway** — objetos que respondem às solicitações que chegam ao processo, como controladores REST ou manipuladores de mensagens AMQP;
-   **Outbound gateway** — objetos que gerenciam interações fora do processo em nome de objetos principais, como acessar um banco de dados ou enviar uma mensagem a um registrador;

**Projeto:**

![](https://miro.medium.com/v2/resize:fit:331/0*3MCoI57PbkAkwh5t.png)

**Referências**:

[https://reflectoring.io/spring-hexagonal/](https://reflectoring.io/spring-hexagonal/)  
[https://netflixtechblog.com/ready-for-changes-with-hexagonal-architecture-b315ec967749](https://netflixtechblog.com/ready-for-changes-with-hexagonal-architecture-b315ec967749)  
[https://blog.octo.com/en/hexagonal-architecture-three-principles-and-an-implementation-example/](https://blog.octo.com/en/hexagonal-architecture-three-principles-and-an-implementation-example/)  
[https://dzone.com/articles/hexagonal-architecture-it-works](https://dzone.com/articles/hexagonal-architecture-it-works)  
[https://medium.com/m4u-tech/ports-adapters-architecture-ou-arquitetura-hexagonal-b4b9904dad1a](https://medium.com/m4u-tech/ports-adapters-architecture-ou-arquitetura-hexagonal-b4b9904dad1a)

## Clean Architecture

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/0*T1jgqal_Z7dqCzTu.png)

A Clean Architecture, representada por um diagrama com camadas circulares concêntricas, foi criada por [Robert C. Martin(“Uncle Bob”)](https://pt.wikipedia.org/wiki/Robert_Cecil_Martin) e promovida em seu livro [Clean Architecture: A Craftsman’s Guide to Software Structure](https://www.amazon.com.br/Clean-Architecture-Craftsmans-Software-Structure/dp/0134494164).

Um objetivo importante da Clean Architecture é fornecer aos desenvolvedores uma maneira de organizar o código de forma que encapsule a lógica de negócios, mas mantenha-o separado do mecanismo de entrega, ou seja, promove o isolamento das camadas, para que a substituição dos componentes na camada sejam fáceis e não afetem todo o sistema

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/0*o9VhAkLT-v3c_Zh1.png)

**Algumas camadas importantes:**

-   **Framework e Drivers —** É a camada mais externa, protege o sistema das mudanças de detalhes;
-   **Interface Adapters** — camada onde reside os presenters, controles, gateways e repositories;
-   **Application Business Rules** — É responsável pelo processamento das informações, é onde ficam os casos de uso;
-   **Enterprise Business Rules**— Camada das _entities_ onde ficam os códigos de regra de negócio à nível de negócio;

**Projeto:**

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/0*SlRIy7-G_XqB7LzW.png)

**Referências**:

[https://www.c-sharpcorner.com/article/clean-architecture-and-cqrs-pattern/](https://www.c-sharpcorner.com/article/clean-architecture-and-cqrs-pattern/)  
[https://proandroiddev.com/clean-architecture-data-flow-dependency-rule-615ffdd79e29?gi=9b9825a55bd9](https://proandroiddev.com/clean-architecture-data-flow-dependency-rule-615ffdd79e29?gi=9b9825a55bd9)  
[https://stackoverflow.com/questions/64601112/clean-architecture-data-changes-fragility](https://stackoverflow.com/questions/64601112/clean-architecture-data-changes-fragility)  
[https://engsoftmoderna.info/artigos/arquitetura-limpa.html](https://engsoftmoderna.info/artigos/arquitetura-limpa.html)  
[https://mayellecarvalho.medium.com/arquitetura-limpa-o-melhor-da-arquitetura-em-camadas-7c945715ca64](https://mayellecarvalho.medium.com/arquitetura-limpa-o-melhor-da-arquitetura-em-camadas-7c945715ca64)  
[https://www.codingblocks.net/podcast/clean-architecture-components-and-component-cohesion/](https://www.codingblocks.net/podcast/clean-architecture-components-and-component-cohesion/)  
[https://sensedia.com/conteudo/padrao-de-arquitetura-hexagonal/](https://sensedia.com/conteudo/padrao-de-arquitetura-hexagonal/)

![](https://miro.medium.com/v2/resize:fit:275/0*5S5PibseGNK-c34c)

Tudo que coloquei vem de material facilmente coletado na internet, pelos links que deixei você poderá se aprofundar nos conteúdos. Essa parte dá pra concluirmos com um texto do Uncle Bob

> “Embora todas essas arquiteturas variem de alguma forma em seus detalhes, elas sao muito similares. Todas têm o mesmo objetivo: a separação das preocupações. Todas realizam essa separação ao dividirem o software em camadas” (Uncle Bob)

Só temos que ter em mente que tudo isso foi bastante influenciado pela necessidade de termos componentes entregáveis de forma que não afetasse a entrega de um componente anterior, todavia, ter componentes isolados com seu próprio fluxo de entrega (CI/CD) tem seu custo. Ter muitas camadas tem seu custo. Estamos cada vez mais indo na direção de construirmos pedaços menores de componentes entregáveis (microservice, nanoservice) o que às vezes justifica uma estrutura menos fatiada, na pegada do [explícito e melhor que implícito](https://www.python.org/dev/peps/pep-0020/), por exemplo, um [AWS Lambda](https://aws.amazon.com/pt/lambda/) que vai em um endpoint e salva o resultado em um banco, pode ser [estupidamente simples](https://pt.wikipedia.org/wiki/Princ%C3%ADpio_KISS), sem firulas. O importante é que saibamos evoluir algo sem comprometer as peças do jogo.

![](https://miro.medium.com/v2/resize:fit:607/0*mjQB2WIh277a8_fU.jpg)

Uncle Bob — Tension Diagram for Component Cohesion ( REP — Reuse / Release Equivalence Principle, CCP — Common Closure Principle, CRP — Common Reuse Principle )

## Frontend

De bônus irei deixar alguma coisa de front, onde, nos dias de hoje, é uma parte do sistema que tende a ser bastante acoplada a algum [framework](https://hackr.io/blog/best-javascript-frameworks).

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/0*ebEvL81qN1fugjAZ)

[Adrià Fontcuberta](https://medium.com/u/69b218da2d74?source=post_page---user_mention--a4c55749a7eb---------------------------------------)

[https://noti.st/afontcu/JHr6wz#s5Uo7px](https://noti.st/afontcu/JHr6wz#s5Uo7px)

Essa imagem que peguei do material do [@afontcu](https://noti.st/afontcu), já resume bem como as coisas podem ser, como o framework escolhido pode ficar longe das camadas mais internas, mesmo no Frontend.

**Referências**:

[https://medium.com/game-development-stuff/ddd-hexagonal-architecture-and-frontend-what-is-this-all-about-e1568a9053c4](https://medium.com/game-development-stuff/ddd-hexagonal-architecture-and-frontend-what-is-this-all-about-e1568a9053c4)  
[https://dev.to/phodal/clean-architecture-for-frontend-in-action-1aop](https://dev.to/phodal/clean-architecture-for-frontend-in-action-1aop)  
[https://pt.slideshare.net/EveliseVazquez/clean-architecture-frontend](https://pt.slideshare.net/EveliseVazquez/clean-architecture-frontend)  
[https://medium.com/@rostislavdugin/the-clean-architecture-using-react-and-typescript-a832662af803](https://medium.com/@rostislavdugin/the-clean-architecture-using-react-and-typescript-a832662af803)  
[https://noti.st/afontcu/JHr6wz#s5Uo7px](https://noti.st/afontcu/JHr6wz#s5Uo7px)

![](https://miro.medium.com/v2/resize:fit:275/0*5S5PibseGNK-c34c)

## Colocando tudo junto

Mesmo depois de ter lido toda essa cachoeira de sopa de letrinha ainda se sente perdido? Separei 2 conteúdos que mostram bem mastigado cada peça desse jogo de montar.

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/0*wsHfTL-ZAj-iXtQo)

[**@hgraca**](https://herbertograca.com/)**\-** [https://herbertograca.com/2017/11/16/explicit-architecture-01-ddd-hexagonal-onion-clean-cqrs-how-i-put-it-all-together/](https://herbertograca.com/2017/11/16/explicit-architecture-01-ddd-hexagonal-onion-clean-cqrs-how-i-put-it-all-together/)

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/1*T9cCd2o5Qa02qq17EZJrcg.png)

[Victor Rentea](https://medium.com/u/48c89f0c4c8f?source=post_page---user_mention--a4c55749a7eb---------------------------------------)

— [https://www.youtube.com/watch?v=tMHO7\_RLxgQ&ab\_channel=Devoxx](https://www.youtube.com/watch?v=tMHO7_RLxgQ&ab_channel=Devoxx)

![](https://miro.medium.com/v2/resize:fit:275/0*5S5PibseGNK-c34c)

**Material extra para leitura:**

[

## Software Architecture: The 5 Patterns You Need to Know - DZone Microservices

### When I was attending night school to become a programmer, I learned several design patterns: singleton, repository…

dzone.com



](https://dzone.com/articles/software-architecture-the-5-patterns-you-need-to-k?source=post_page-----a4c55749a7eb---------------------------------------)

[Youtube: Coesão, Acoplamento e Granularidade](https://www.youtube.com/watch?v=OTDjLto9LvA&ab_channel=Andr%C3%A9Santanch%C3%A8)

[https://robsoncastilho.com.br/2013/05/01/principios-solid-principio-da-inversao-de-dependencia-dip/](https://robsoncastilho.com.br/2013/05/01/principios-solid-principio-da-inversao-de-dependencia-dip/)

[https://thedomaindrivendesign.io/what-is-tactical-design/](https://thedomaindrivendesign.io/what-is-tactical-design/)

[https://thedomaindrivendesign.io/what-is-strategic-design/](https://thedomaindrivendesign.io/what-is-strategic-design/)