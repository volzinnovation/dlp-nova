// Exact named-answer adapter for the Bach ontology and family-maintenance study.
// Uses the separately pinned HermiT / OWLAPI runtime of owl_bridge.py.
// Every state is an independent rebuild; no incremental HermiT claim is made.
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.File;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import org.semanticweb.HermiT.Reasoner;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.IRI;
import org.semanticweb.owlapi.model.OWLAxiom;
import org.semanticweb.owlapi.model.OWLClass;
import org.semanticweb.owlapi.model.OWLClassExpression;
import org.semanticweb.owlapi.model.OWLDataFactory;
import org.semanticweb.owlapi.model.OWLEquivalentClassesAxiom;
import org.semanticweb.owlapi.model.OWLNamedIndividual;
import org.semanticweb.owlapi.model.OWLObjectProperty;
import org.semanticweb.owlapi.model.OWLOntology;
import org.semanticweb.owlapi.model.OWLOntologyManager;
import org.semanticweb.owlapi.model.parameters.Imports;
import org.semanticweb.owlapi.reasoner.OWLReasoner;

public final class BachOwlBridge {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#";
    private static final String RDFS = "http://www.w3.org/2000/01/rdf-schema#";
    private static final String OWL = "http://www.w3.org/2002/07/owl#";

    private static double seconds(long started) {
        return (System.nanoTime() - started) / 1_000_000_000.0;
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node.get(field);
        if (value == null || !value.isTextual() || value.asText().isEmpty()) {
            throw new IllegalArgumentException("Expected nonempty string: " + field);
        }
        return value.asText();
    }

    private static IRI iri(String value, String namespace) {
        if (value.startsWith("rdf:")) return IRI.create(RDF + value.substring(4));
        if (value.startsWith("rdfs:")) return IRI.create(RDFS + value.substring(5));
        if (value.startsWith("owl:")) return IRI.create(OWL + value.substring(4));
        if (value.contains(":")) return IRI.create(value);
        return IRI.create(namespace + value);
    }

    private static final class Query {
        final String id;
        final String method;
        final List<IRI> arguments = new ArrayList<IRI>();
        final OWLClassExpression expression;

        Query(JsonNode node, String namespace) throws Exception {
            id = text(node, "id");
            method = text(node, "method");
            JsonNode args = node.get("arguments");
            if (args != null) {
                if (!args.isArray()) throw new IllegalArgumentException("arguments must be an array");
                for (JsonNode arg : args) {
                    if (!arg.isTextual()) {
                        throw new IllegalArgumentException("Only named IRI arguments are supported");
                    }
                    arguments.add(iri(arg.asText(), namespace));
                }
            }
            int expected;
            switch (method) {
                case "instances_expression": expected = 0; break;
                case "instances": case "types": case "property_pairs":
                case "is_symmetric": case "is_transitive": case "is_satisfiable":
                    expected = 1; break;
                case "property_values": case "subsumes": case "property_subsumes":
                    expected = 2; break;
                case "entails": expected = 3; break;
                default: throw new IllegalArgumentException("Unsupported query method: " + method);
            }
            if (arguments.size() != expected) {
                throw new IllegalArgumentException(method + " requires " + expected + " arguments");
            }
            expression = method.equals("instances_expression")
                ? expression(node, namespace) : null;
        }
    }

    private static OWLClassExpression expression(JsonNode query, String namespace) throws Exception {
        // The helper is parsed independently. Its marker never enters the tested ontology.
        OWLOntologyManager manager = OWLManager.createOWLOntologyManager();
        OWLOntology helper = manager.loadOntologyFromOntologyDocument(
            new File(text(query, "expression_file")));
        if (!helper.getImportsDeclarations().isEmpty()) {
            throw new IllegalArgumentException("Expression helpers must not import ontologies");
        }
        OWLClass marker = manager.getOWLDataFactory().getOWLClass(
            iri(text(query, "expression_class"), namespace));
        Set<OWLEquivalentClassesAxiom> axioms = helper.getEquivalentClassesAxioms(marker);
        if (axioms.size() != 1 || helper.getLogicalAxiomCount() != 1) {
            throw new IllegalArgumentException("Expression helper must have exactly one logical axiom");
        }
        Set<OWLClassExpression> expressions = new HashSet<OWLClassExpression>(
            axioms.iterator().next().getClassExpressions());
        if (expressions.size() != 2 || !expressions.remove(marker)) {
            throw new IllegalArgumentException("Expression helper must equate its marker with one expression");
        }
        OWLClassExpression result = expressions.iterator().next();
        if (result.getClassesInSignature().contains(marker)) {
            throw new IllegalArgumentException("Expression must not contain its helper marker");
        }
        manager.removeOntology(helper);
        return result;
    }

    private static List<String> names(Set<OWLNamedIndividual> individuals) {
        TreeSet<String> result = new TreeSet<String>();
        for (OWLNamedIndividual individual : individuals) result.add(individual.getIRI().toString());
        return new ArrayList<String>(result);
    }

    private static OWLObjectProperty property(OWLDataFactory factory, OWLOntology ontology, IRI name) {
        if (ontology.containsDataPropertyInSignature(name, Imports.INCLUDED)) {
            throw new IllegalArgumentException("This named-answer adapter supports object properties only: " + name);
        }
        return factory.getOWLObjectProperty(name);
    }

    private static boolean entailed(OWLReasoner reasoner, OWLAxiom axiom) {
        if (!reasoner.isEntailmentCheckingSupported(axiom.getAxiomType())) {
            throw new IllegalArgumentException("Reasoner cannot check this axiom: " + axiom.getAxiomType());
        }
        return reasoner.isEntailed(axiom);
    }

    private static Object answer(Query query, OWLReasoner reasoner, OWLOntology ontology,
                                 OWLDataFactory factory) {
        List<IRI> args = query.arguments;
        switch (query.method) {
            case "instances":
                return names(reasoner.getInstances(factory.getOWLClass(args.get(0)), false).getFlattened());
            case "instances_expression":
                return names(reasoner.getInstances(query.expression, false).getFlattened());
            case "types": {
                TreeSet<String> classes = new TreeSet<String>();
                for (OWLClass value : reasoner.getTypes(
                        factory.getOWLNamedIndividual(args.get(0)), false).getFlattened()) {
                    classes.add(value.getIRI().toString());
                }
                return new ArrayList<String>(classes);
            }
            case "property_values":
                return names(reasoner.getObjectPropertyValues(factory.getOWLNamedIndividual(args.get(0)),
                    property(factory, ontology, args.get(1))).getFlattened());
            case "property_pairs": {
                OWLObjectProperty predicate = property(factory, ontology, args.get(0));
                List<List<String>> rows = new ArrayList<List<String>>();
                // Enumerate only ontology-named subjects; generated existential witnesses are excluded.
                for (String subject : names(ontology.getIndividualsInSignature(Imports.INCLUDED))) {
                    for (String object : names(reasoner.getObjectPropertyValues(
                            factory.getOWLNamedIndividual(IRI.create(subject)), predicate).getFlattened())) {
                        rows.add(Arrays.asList(subject, object));
                    }
                }
                return rows;
            }
            case "entails": {
                OWLNamedIndividual subject = factory.getOWLNamedIndividual(args.get(0));
                if (args.get(1).toString().equals(RDF + "type")) {
                    return entailed(reasoner, factory.getOWLClassAssertionAxiom(
                        factory.getOWLClass(args.get(2)), subject));
                }
                if (args.get(1).toString().equals(OWL + "sameAs")) {
                    return entailed(reasoner, factory.getOWLSameIndividualAxiom(
                        subject, factory.getOWLNamedIndividual(args.get(2))));
                }
                if (args.get(1).toString().equals(OWL + "differentFrom")) {
                    return entailed(reasoner, factory.getOWLDifferentIndividualsAxiom(
                        subject, factory.getOWLNamedIndividual(args.get(2))));
                }
                return entailed(reasoner, factory.getOWLObjectPropertyAssertionAxiom(
                    property(factory, ontology, args.get(1)), subject,
                    factory.getOWLNamedIndividual(args.get(2))));
            }
            case "subsumes":
                // Public manifest arguments are (superclass, subclass).
                return entailed(reasoner, factory.getOWLSubClassOfAxiom(
                    factory.getOWLClass(args.get(1)), factory.getOWLClass(args.get(0))));
            case "property_subsumes":
                return entailed(reasoner, factory.getOWLSubObjectPropertyOfAxiom(
                    property(factory, ontology, args.get(1)), property(factory, ontology, args.get(0))));
            case "is_symmetric":
                return entailed(reasoner, factory.getOWLSymmetricObjectPropertyAxiom(
                    property(factory, ontology, args.get(0))));
            case "is_transitive":
                return entailed(reasoner, factory.getOWLTransitiveObjectPropertyAxiom(
                    property(factory, ontology, args.get(0))));
            case "is_satisfiable":
                return reasoner.isSatisfiable(factory.getOWLClass(args.get(0)));
            default: throw new IllegalArgumentException("Unsupported query method: " + query.method);
        }
    }

    private static ObjectNode state(JsonNode spec, String namespace, int index) throws Exception {
        long started = System.nanoTime();
        JsonNode querySpecs = spec.get("queries");
        if (querySpecs == null || !querySpecs.isArray()) {
            throw new IllegalArgumentException("Each state must contain a queries array");
        }
        List<Query> queries = new ArrayList<Query>();
        Set<String> identifiers = new HashSet<String>();
        for (JsonNode querySpec : querySpecs) {
            Query query = new Query(querySpec, namespace);
            if (!identifiers.add(query.id)) throw new IllegalArgumentException("Duplicate query id: " + query.id);
            queries.add(query);
        }
        double preparationSeconds = seconds(started);
        started = System.nanoTime();
        OWLOntologyManager manager = OWLManager.createOWLOntologyManager();
        OWLOntology ontology = manager.loadOntologyFromOntologyDocument(new File(text(spec, "ontology")));
        double loadSeconds = seconds(started);
        started = System.nanoTime();
        OWLReasoner reasoner = new Reasoner.ReasonerFactory().createReasoner(ontology);
        double constructSeconds = seconds(started);
        ObjectNode output = JSON.createObjectNode();
        output.put("id", spec.has("id") ? text(spec, "id") : "state-" + index);
        output.put("update_strategy", "fresh-rebuild");
        output.put("query_preparation_seconds", preparationSeconds);
        output.put("load_seconds", loadSeconds);
        output.put("construct_seconds", constructSeconds);
        output.put("reasoner_version", reasoner.getReasonerVersion().toString());
        double querySeconds = 0;
        try {
            started = System.nanoTime();
            boolean consistent = reasoner.isConsistent();
            double consistencySeconds = seconds(started);
            output.put("consistent", consistent);
            output.put("consistency_seconds", consistencySeconds);
            output.put("named_individual_count", ontology.getIndividualsInSignature(Imports.INCLUDED).size());
            output.put("logical_axiom_count", ontology.getLogicalAxiomCount());
            ArrayNode results = output.putArray("queries");
            if (consistent) {
                for (Query query : queries) {
                    started = System.nanoTime();
                    Object value = answer(query, reasoner, ontology, manager.getOWLDataFactory());
                    double elapsed = seconds(started);
                    querySeconds += elapsed;
                    ObjectNode row = results.addObject();
                    row.put("id", query.id);
                    row.put("method", query.method);
                    row.put("seconds", elapsed);
                    row.set("answer", JSON.valueToTree(value));
                }
            }
            output.put("query_status", consistent ? "complete" : "skipped-inconsistent");
            output.put("query_seconds", querySeconds);
            output.put("task_seconds", loadSeconds + constructSeconds + consistencySeconds + querySeconds);
            output.put("prepared_task_seconds", preparationSeconds + loadSeconds + constructSeconds
                + consistencySeconds + querySeconds);
        } finally {
            started = System.nanoTime();
            reasoner.dispose();
            manager.removeOntology(ontology);
            output.put("dispose_seconds", seconds(started));
        }
        return output;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("Expected one JSON request file");
        JsonNode request = JSON.readTree(new File(args[0]));
        String namespace = text(request, "namespace");
        JsonNode states = request.get("states");
        if (states == null) states = JSON.createArrayNode().add(request);
        if (!states.isArray() || states.size() == 0) {
            throw new IllegalArgumentException("states must be a nonempty array");
        }
        ObjectNode output = JSON.createObjectNode();
        output.put("adapter", "BachOwlBridge");
        output.put("adapter_source", "benchmarks/BachOwlBridge.java");
        output.put("adapter_version", 1);
        output.put("configuration", "hermit");
        output.put("java_version", System.getProperty("java.version"));
        output.put("update_strategy", "fresh-rebuild");
        output.put("query_timing", "complete answer retrieval and sorting; helper parsing excluded");
        ArrayNode results = output.putArray("states");
        Set<String> identifiers = new HashSet<String>();
        int index = 0;
        for (JsonNode spec : states) {
            ObjectNode result = state(spec, namespace, index++);
            if (!identifiers.add(result.get("id").asText())) {
                throw new IllegalArgumentException("Duplicate state id: " + result.get("id").asText());
            }
            results.add(result);
        }
        System.out.println(JSON.writeValueAsString(output));
    }
}
