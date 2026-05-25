# **_Padrões de projetos_**

[

![Pablo Ruiz](https://miro.medium.com/v2/resize:fill:32:32/1*RMKq8JyZaarGZVQ8mEwFmA.jpeg)





](https://medium.com/@devPablo?source=post_page---byline--8a37dfee616a---------------------------------------)

[Pablo Ruiz](https://medium.com/@devPablo?source=post_page---byline--8a37dfee616a---------------------------------------)

Follow

11 min read

·

Oct 20, 2024

[

](https://medium.com/m/signin?actionUrl=https%3A%2F%2Fmedium.com%2F_%2Fvote%2Fp%2F8a37dfee616a&operation=register&redirect=https%3A%2F%2Fmedium.com%2F%40devPablo%2Fpadr%25C3%25B5es-de-projetos-8a37dfee616a&user=Pablo+Ruiz&userId=ddf99ff14c74&source=---header_actions--8a37dfee616a---------------------clap_footer------------------)

[](https://medium.com/m/signin?actionUrl=https%3A%2F%2Fmedium.com%2F_%2Fbookmark%2Fp%2F8a37dfee616a&operation=register&redirect=https%3A%2F%2Fmedium.com%2F%40devPablo%2Fpadr%25C3%25B5es-de-projetos-8a37dfee616a&source=---header_actions--8a37dfee616a---------------------bookmark_footer------------------)

Share

O que são padrões de projeto ? Padrões de projetos são soluções tipicas para problemas comuns em projetos de software. Podemos fazer uma analogia com receitas.  
Padrões de projetos são como receitas, podemos replicar ao pé da letra ou podemos dar o nosso toque. E como receitas podemos escolher a melhor receita para cada tipo de ocasião. Podemos classificar os padrões em três tipos:

-   **_Criacionais_**

Fornecem mecanismos de criação de objetos que aumentam a flexibilidade e a reutilização do código.

-   **_Estruturais_**

Explicam como montar objetos e classes maiores, enquanto ainda mantém as estruturas flexiveis e eficientes.

-   **_Comportamentais_**

Cuidam da comunicação eficiente e da assinalção de responsabilidades entre objetos.

Nesse artigo eu foi focar nos padrões da categoria criacionais, esses padrões são:

-   Factory Method
-   Abstract Factory
-   Builder
-   Prototype
-   Singleton

Esses padrões apresentam várias soluções para criações de objetos, visando o aumento da flexibilidade e reutilização de código.

## **_Factory Method_**

O Factory Method fornece uma interface para criar objetos em uma superclasse, mas permite que as subclasses alterem o tipo de objetos que serão criados. A ideia é separar o código de construção do produto do código que realmente usa o produto. Isso deixa mais fácil estender o código de construção do produto independentemente do restante do código.

Vamos utilizar esse padrão em ocasiões onde precisaremos lidar com objetos grandes e pesados, como conexões com bancos de dados, sistemas de arquivos e recursos de rede.

Um ponto negativo é a complexidade, pois iremos inserir muitas subclasses novas para implementar o padrão.

Agora que já sabemos um pouco mais sobre o padrão, vamos entender melhor sua estrutura.

-   Vamos começar criando uma interface. Essa interface será comum a todos os objetos que podem ser produzidos pelo criador e suas subclasses. Ela vai representar as características do produto.
-   Logo após, precisamos criar classes concretas que vão representar o produto. Essas classes irão implementar a interface.
-   Vamos criar nossa classe que vai representar o nosso “criador”. Essa classe pode ser abstrata, pois assim forçamos todas as subclasses a implementar suas próprias versões do método. Mesmo chamando a classe de “criador”, sua principal responsabilidade não é criar, mas sim dissociar essa lógica das classes concretas de produtos.
-   VictorianChairPor último, vamos criar as classes concretas que vão representar nossos objetos. Essas classes irão sobrescrever os métodos de fábrica base.

O diagrama mostra a implementação do padrão **Factory Method** de forma clara.

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/1*TCOi1MNjVX_xoxZEOKcRXg.png)

Factory method

-   **Transport** é a interface comum para todos os tipos de transporte.
-   As classes **LogisticsMaritime** e **LogisticsRoad** implementam essa interface, representando diferentes tipos de transporte, cada uma com suas características.
-   **Logistic** é a classe abstrata que define o método `createTransport()`, mas deixa a criação dos objetos para as subclasses concretas.
-   As fábricas concretas, **RoadFactory** e **MaritimeFactory**, implementam `createTransport()` para criar os objetos específicos (rodoviário ou marítimo).

  
public interface Transport {  
  
    public String getVehicleRegistration();  
  
    public boolean getDeliver();  
  
}  
  
public class LogisticsMaritime implements Transport {  
  
    private String vehicleLicencePlate;  
    private boolean delivery;  
  
    public LogisticsMaritime(String vehicleLicencePlate, boolean delivery) {  
        this.vehicleLicencePlate = vehicleLicencePlate;  
        this.delivery = delivery;  
    }  
  
    @Override  
    public String getVehicleRegistration() {  
        return vehicleLicencePlate;  
    }  
  
    public void setVehicleLicencePlate(String vehicleLicencePlate) {  
        this.vehicleLicencePlate = vehicleLicencePlate;  
    }  
  
    @Override  
    public boolean getDeliver() {  
        return delivery;  
    }  
  
    public void setDelivery(boolean delivery) {  
        this.delivery = delivery;  
    }  
}  
  
public class LogisticsRoad implements Transport {  
  
    private String vehicleRegistration;  
    private boolean delivery;  
  
    public LogisticsRoad(String vehicleRegistration, boolean delivery) {  
        this.vehicleRegistration = vehicleRegistration;  
        this.delivery = delivery;  
    }  
  
    @Override  
    public String getVehicleRegistration() {  
        return vehicleRegistration;  
    }  
  
    public void setVehicleRegistration(String vehicleRegistration) {  
        this.vehicleRegistration = vehicleRegistration;  
    }  
  
    @Override  
    public boolean getDeliver() {  
        return delivery;  
    }  
  
    public void setDelivery(boolean delivery) {  
        this.delivery = delivery;  
    }  
}  
  
  
public abstract class Logistic {  
  
    public abstract Transport createTransport();  
  
    public void planDelivery() {  
        Transport transport \= createTransport();  
        System.out.println("Iniciando o planejamento de entrega.");  
        System.out.println("Entrega realizada: " + transport.getDeliver());  
    }  
}  
  
public class MaritimeFactory extends Logistic {  
  
    private String vehicleRegistration;  
    private boolean delivery;  
  
    public MaritimeFactory(String vehicleRegistration, boolean delivery) {  
        this.vehicleRegistration = vehicleRegistration;  
        this.delivery = delivery;  
    }  
  
    @Override  
    public Transport createTransport() {  
        return new LogisticsMaritime(vehicleRegistration, delivery);  
    }  
  
}  
  
  
public class RoadFactory extends Logistic {  
  
    private String vehicleRegistration;  
    private boolean delivery;  
  
    public RoadFactory(String vehicleRegistration, boolean delivery) {  
        this.vehicleRegistration = vehicleRegistration;  
        this.delivery = delivery;  
    }  
  
    @Override  
    public Transport createTransport() {  
        return new LogisticsRoad(vehicleRegistration, delivery);  
    }  
  
}

## Abstract Factory

O padrão **Abstract Factory** fornece uma interface para criar famílias de objetos relacionados ou dependentes sem a necessidade de especificar suas classes concretas.  
Esse padrão pode ser útil quando precisamos criar múltiplos produtos relacionados que devem funcionar juntos. Por exemplo, ao criar um veículo, pode ser necessário um tipo específico de motor que corresponda a esse modelo. O **Abstract Factory** garante que essas criações sejam consistentes.

No entanto, um ponto fraco dessa abordagem é o aumento da complexidade do código, já que será necessário manter várias interfaces e classes que as implementam. Um dos benefícios principais desse padrão é que ele segue o **Princípio da Responsabilidade Única (SRP)**, pois centraliza o código de criação em um único lugar.

Agora que já entendemos um pouco mais sobre o padrão, vamos explorar sua estrutura.

Agora que já sabemos um pouco mais sobre o padrão, vamos entender melhor sua estrutura.

-   Precisamos estabelecer as interfaces que fazem parte de uma familia de produtos.
-   Em seguida, criaremos implementações dessas interfaces em classes concretas que representarão cada produto.
-   Criaremos uma nova interface que representa-ra nossa fábrica abstrata, ela vai ser resposavel por declarar métodos de construção dos produtos abstratos.
-   Por fim, desenvolveremos nossas fábricas concretas, que implementarão essa interface abstrata. Embora as fábricas concretas instanciem produtos específicos, as assinaturas de seus métodos devem retornar os produtos abstratos correspondentes. Isso garante que o código cliente não fique acoplado a uma variante específica do produto.

O diagrama mostra a implementação do padrão **Abstract Factory** de forma clara.

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/1*GPPrXwOB5Wv50UqmLtEYwg.png)

**Abstract Factory**

-   As interfaces `Chair`, `Sofa`, e `CoffeTable` e suas implementações vitorianas.
-   A interface `FurnitureFactory` e sua implementação `VictorianFurnitureFactory`, com métodos para criar os móveis.
-   A associação da fábrica com os móveis que ela cria.

public interface Chair {  
  
}  
  
public interface Sofa {  
}  
  
public interface CoffeTable {  
}  
  
public class VictorianChair implements Chair {  
}  
  
public class VictorianSofa implements Sofa {  
}  
  
public class VictorianCoffeTable implements CoffeTable {  
}  
  
public interface FurnitureFactory {  
  
    Chair createChair();  
  
    CoffeTable createCoffeTable();  
  
    Sofa CreateSofa();  
}  
  
public class VictorianFurnitureFactory implements FurnitureFactory {  
  
  
    @Override  
    public Chair createChair() {  
        return new VictorianChair();  
    }  
  
    @Override  
    public CoffeTable createCoffeTable() {  
        return new VictorianCoffeTable();  
    }  
  
    @Override  
    public Sofa CreateSofa() {  
        return new VictorianSofa();  
    }  
}

## Builder

O padrão Builder é um padrão de criação que permite construir objetos complexos de maneira passo a passo. Ele nos oferece a possibilidade de produzir diferentes representações de um objeto utilizando o mesmo código de construção.

## Get Pablo Ruiz’s stories in your inbox

Join Medium for free to get updates from this writer.

Subscribe

Subscribe

Remember me for faster sign in

Esse padrão é especialmente útil quando precisamos ter a flexibilidade de construir objetos em partes ou quando eles podem sofrer mudanças ao longo do tempo. Para ilustrar melhor o conceito, podemos usar o exemplo da construção de uma casa.

Ao construir uma casa pequena, média ou grande, o processo segue basicamente os mesmos passos; o que muda são as dimensões e os detalhes específicos de cada construção. O Builder oferece essa flexibilidade ao permitir que o processo de construção seja personalizado para cada caso, sem alterar a lógica principal.

Agora que entendemos o objetivo do padrão, vamos explorar sua estrutura:

-   Para iniciar vamos criar uma interface que seja responsável por centralizar as etapas de construção em comum.
-   Depois, criamos construtores concretos, que podem produzir produtos que não seguem necessariamente a mesma interface comum. Por exemplo, podemos ter classes que representam uma **Casa** e um **Sítio**.
-   Vamos criar uma classe concretaque represente o produto criado pelo builder.
-   Por fim, uma classe **Diretor** é responsável por definir a ordem das etapas de construção, garantindo que o objeto seja construído de forma consistente.

O diagrama mostra a implementação do padrão **Builder** de forma clara.

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/1*9PzhMmiy7iaVGh0WoMUNiw.png)

**Builder**

-   A interface **Builder** define os métodos para construir as partes de uma casa, como `setAddress()`, `setNumberOfRooms()`, `setHasGarage()`, e `setHasSwimmingPool()`.
-   As classes **HouseMediumBuilder** e **HouseLargeBuilder** implementam essa interface, construindo casas de tamanho médio e grande, respectivamente.
-   A classe **House** representa o produto final, com atributos como `address`, `numberOfRooms`, `hasGarage`, e `hasSwimmingPool`.
-   O **Diretor** controla a ordem de construção, usando um `Builder` para criar uma casa completa (média ou grande).

public interface Builder {  
  
    void reset();  
    Builder setAddress(String address);  
    Builder setRooms(int numberOfRooms);  
    Builder setGarage(boolean hasGarage);  
    Builder setSize(double sizeInSquareMeters);  
    House build();  
  
}  
  
public class HouseMediumBuilder implements Builder {  
  
    private House house;  
  
    @Override  
    public void reset() {  
        this.house = new House();  
    }  
  
    @Override  
    public Builder setAddress(String address) {  
        house.setAddress(address);  
        return this;  
    }  
  
    @Override  
    public Builder setRooms(int numberOfRooms) {  
        house.setNumberOfRooms(numberOfRooms);  
        return this;  
    }  
  
    @Override  
    public Builder setGarage(boolean hasGarage) {  
        house.setHasGarage(hasGarage);  
        return this;  
    }  
  
    @Override  
    public Builder setSize(double sizeInSquareMeters) {  
        house.setSizeInSquareMeters(sizeInSquareMeters);  
        return this;  
    }  
  
    @Override  
    public House build() {  
        return this.house;  
    }  
}  
  
public class HouseLargeBuilder implements Builder {  
  
    private House house;  
  
    @Override  
    public void reset() {  
        this.house = new House();  
    }  
  
    @Override  
    public Builder setAddress(String address) {  
        house.setAddress(address);  
        return this;  
    }  
  
    @Override  
    public Builder setRooms(int numberOfRooms) {  
        house.setNumberOfRooms(numberOfRooms);  
        return this;  
    }  
  
    @Override  
    public Builder setGarage(boolean hasGarage) {  
        house.setHasGarage(hasGarage);  
        return this;  
    }  
  
    @Override  
    public Builder setSize(double sizeInSquareMeters) {  
        house.setSizeInSquareMeters(sizeInSquareMeters);  
        return this;  
    }  
  
    @Override  
    public House build() {  
        return this.house;  
    }  
}  
  
public class House {  
  
    private String address;  
    private int numberOfRooms;  
    private double sizeInSquareMeters;  
    private boolean hasGarage;  
  
    public House() {  
    }  
  
    public House(String address, boolean hasGarage, double sizeInSquareMeters, int numberOfRooms) {  
        this.address = address;  
        this.hasGarage = hasGarage;  
        this.sizeInSquareMeters = sizeInSquareMeters;  
        this.numberOfRooms = numberOfRooms;  
    }  
  
    public String getAddress() {  
        return address;  
    }  
  
    public void setAddress(String address) {  
        this.address = address;  
    }  
  
    public double getSizeInSquareMeters() {  
        return sizeInSquareMeters;  
    }  
  
    public void setSizeInSquareMeters(double sizeInSquareMeters) {  
        this.sizeInSquareMeters = sizeInSquareMeters;  
    }  
  
    public boolean isHasGarage() {  
        return hasGarage;  
    }  
  
    public void setHasGarage(boolean hasGarage) {  
        this.hasGarage = hasGarage;  
    }  
  
    public int getNumberOfRooms() {  
        return numberOfRooms;  
    }  
  
    public void setNumberOfRooms(int numberOfRooms) {  
        this.numberOfRooms = numberOfRooms;  
    }  
}  
  
public class Director {  
  
     private Builder builder;  
  
    public void setBuilder(Builder builder) {  
        this.builder = builder;  
    }  
  
    public House constructMediumHouse(String address, int numberOfRooms, double sizeInSquareMeters, boolean hasGarage) {  
        builder.reset();  
        builder.setAddress(address)  
                .setRooms(numberOfRooms)  
                .setSize(sizeInSquareMeters)  
                .setGarage(hasGarage);  
        return builder.build();  
    }  
  
    public House constructLargeHouse(String address, int numberOfRooms, double sizeInSquareMeters, boolean hasGarage) {  
        builder.reset();  
        builder.setAddress(address)  
                .setRooms(numberOfRooms)  
                .setSize(sizeInSquareMeters)  
                .setGarage(hasGarage);  
        return builder.build();  
    }  
}

## Prototype

O padrão **Prototype** permite copiar objetos existentes sem que o código dependa diretamente de suas classes. Podemos imaginar um cenário onde precisamos fazer uma cópia exata de um objeto. Como poderíamos realizar isso? A solução básica seria criar um novo objeto da mesma classe e copiar manualmente todos os valores do objeto original. No entanto, isso pode ser problemático, pois alguns objetos possuem atributos privados ou estruturas internas complexas que dificultam essa cópia manual.

O padrão Prototype resolve exatamente esse problema, pois delega o processo de clonagem ao próprio objeto que está sendo clonado. Em vez de expor detalhes internos do objeto, o objeto original gerencia sua própria clonagem de maneira segura e encapsulada.

Agora que entendemos o objetivo do padrão, vamos explorar sua estrutura:

-   Para iniciar vamos criar uma interface, ela vai declarar os métodos de clonagem.
-   Em seguida, criamos uma classe concreta que implementa essa interface. Essa classe é responsável por “gerenciar” o processo de clonagem. Qualquer regra de negócio específica para o processo de cópia será concentrada nesta classe.

O diagrama mostra a implementação do padrão **Prototype** de forma clara.

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/1*IgbOz9RNDBD3mfrjy4wdqA.png)

**Prototype**

-   A interface `Prototype` define o método `clone()`, que é responsável por criar e retornar uma cópia do objeto atual.
-   A classe `Car` implementa essa interface, representando um carro com os atributos `model` e `color`. Ela possui um construtor que recebe esses atributos e um construtor de cópia que cria uma nova instância a partir de um carro existente. O método `clone()` retorna um novo objeto `Car` ao utilizar o construtor de cópia.
-   A classe `CarPrototypeRegistry` atua como um registro de protótipos, armazenando diferentes instâncias de `Car` em um mapa (`Map<String, Prototype>`). Ela permite adicionar novos protótipos com o método `addPrototype()` e clonar um protótipo existente por meio do método `getPrototype()`, que retorna uma cópia do carro correspondente à chave fornecida.

public interface Prototype {  
  
    Prototype clone();  
}  
  
public class Car implements Prototype {  
  
    private final String model;  
    private final String color;  
  
    public Car(String model, String color) {  
        this.model = model;  
        this.color = color;  
    }  
  
    public Car(Car car) {  
        this.model = car.model;  
        this.color = car.color;  
    }  
  
    public String getModel() {  
        return model;  
    }  
  
    public String getColor() {  
        return color;  
    }  
  
    @Override  
    public Car clone() {  
        return new Car(this);  
    }  
}  
  
public class CarPrototypeRegistry {  
  
    private Map<String, Prototype> carPrototypes = new HashMap<>();  
  
    public void addPrototype(String key, Prototype prototype) {  
        carPrototypes.put(key, prototype);  
    }  
  
    public Prototype getPrototype(String key) {  
        Prototype prototype \= carPrototypes.get(key);  
        return prototype != null ? prototype.clone() : null;  
    }  
}

## Singleton

É um padrão de projeto criacional que permite garantir que uma classe tenha apenas uma instância enquanto provê um ponto de acesso global para a instância.  
O singleton consegue resolver dois tipos de problemas, ele garante que uma classe tenha apenas uma única instância e fornece um ponto de acesso global para aquela instância.

Podemos pensar no singleton como um acesso global para determinado objeto único, por exemplo  
vamos iamginar um banco central. O banco central representa um pais, e de lá é impresso o dinheiro correto ? O dinheiro pode ser usado no pais todo porém ele é “fabricado” ou “pertecende” a um único lugar.

Alguns dos pontos negativos desse padrão é utilizar ele em ambientes de multithreads, isso  
requer um tratamento especial. E uma dificuldade para escrever testes unitários.

Agora que entendemos o objetivo do padrão, vamos explorar sua estrutura:

-   Primeiramente adicione um campo private estático na classe para o amazenamentoo da instância.
-   Logo após Crie um método de criação pública estático para obter a instância do singleton.
-   Precisaremos implementar a “inicialização preguiçosa” dentro do método estático que criamos. Ele tem como objetivo criar um novo objeto e armazena-lo no campo estático, dessa forma o método sempre irá retornar aquela instância.
-   Vamos precisar criar um construtor privado.

O diagrama mostra a implementação do padrão **Singleton** de forma clara.

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/1*nOz-_RhQey3llUoBO4SI_Q.png)

**Singleton**

. A classe **centralBank** tem:

-   Um campo estático **instance** que é privado (`-`).
-   O método **getInstance()** que retorna a instância do Singleton.
-   O método **centralBankOpen()** , que simula uma operação da classe.

public class CentralBank {  
  
    private static CentralBank instance;  
  
    private CentralBank() {}  
  
    public static synchronized CentralBank getInstancia() {  
        if (instance == null) {  
            instance = new CentralBank();  
        }  
        return instance;  
    }  
  
    public void centralBankOpen() {  
        System.out.println("Central Bank open");  
    }  
}  
  
public class Main {  
  
    public static void main(String\[\] args) {  
        CentralBank centralBank \= CentralBank.getInstancia();  
        centralBank.centralBankOpen();  
    }  
}

Além dos exemplos mencionados sobre padrões de design, podemos ver alguns **design patterns** sendo aplicados em bibliotecas nativas do Java. Aqui estão alguns exemplos notáveis:

-   Singleton: **java.lang.Runtime**
-   Factory method: **java.util.Calendar**
-   Abstract Factory: **javax.xml.parsers.DocumentBuilderFactory**
-   Builder: **java.lang.StringBuilder**
-   Prototype: **java.lang.Object**

Esses exemplos ilustram como os padrões de design criacionais estão profundamente integrados à linguagem Java, fornecendo soluções reutilizáveis e eficientes para problemas comuns no desenvolvimento de software. Entender e aplicar esses padrões não só facilita a manutenção e a escalabilidade do código, mas também aprimora a qualidade geral das soluções desenvolvidas.