// Research adapter for pinned OWLAPI-maintained HermiT 1.4.5.519 / OWLAPI 5.1.9.
// Both engines receive identical RDF/XML; HermiT retains its normal optimizations.
import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.semanticweb.HermiT.Reasoner;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.IRI;
import org.semanticweb.owlapi.model.OWLClass;
import org.semanticweb.owlapi.model.OWLDataFactory;
import org.semanticweb.owlapi.model.OWLNamedIndividual;
import org.semanticweb.owlapi.model.OWLOntology;
import org.semanticweb.owlapi.model.OWLOntologyManager;
import org.semanticweb.owlapi.reasoner.OWLReasoner;

public final class OwlBridge {
    private static double seconds(long started) {
        return (System.nanoTime() - started) / 1_000_000_000.0;
    }

    private static String quote(String value) {
        return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"")
            .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + "\"";
    }

    private static String array(List<String> values) {
        List<String> result = new ArrayList<String>();
        for (String value : values) result.add(quote(value));
        return "[" + String.join(",", result) + "]";
    }

    private static List<String> instances(OWLReasoner reasoner, OWLClass target) {
        List<String> result = new ArrayList<String>();
        for (OWLNamedIndividual value : reasoner.getInstances(target, false).getFlattened()) {
            result.add(value.getIRI().toString());
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("Expected one RDF/XML file");
        long started = System.nanoTime();
        OWLOntologyManager manager = OWLManager.createOWLOntologyManager();
        OWLOntology ontology = manager.loadOntologyFromOntologyDocument(new File(args[0]));
        double loadSeconds = seconds(started);
        OWLDataFactory factory = manager.getOWLDataFactory();
        OWLClass positive = factory.getOWLClass(IRI.create("urn:owl-bridge:C"));
        OWLClass negative = factory.getOWLClass(IRI.create("urn:owl-bridge:D"));
        started = System.nanoTime();
        OWLReasoner reasoner = new Reasoner.ReasonerFactory().createReasoner(ontology);
        double constructSeconds = seconds(started);
        started = System.nanoTime();
        boolean consistent = reasoner.isConsistent();
        double consistencySeconds = seconds(started);
        if (!consistent) throw new IllegalStateException("Generated bridge ontology is inconsistent");
        started = System.nanoTime();
        List<String> positiveRows = instances(reasoner, positive);
        double positiveSeconds = seconds(started);
        started = System.nanoTime();
        List<String> negativeRows = instances(reasoner, negative);
        double negativeSeconds = seconds(started);
        Collections.sort(positiveRows);
        Collections.sort(negativeRows);
        String version = reasoner.getReasonerVersion().toString();
        reasoner.dispose();
        System.out.println("{\"configuration\":\"hermit\",\"consistent\":true,"
            + "\"load_seconds\":" + loadSeconds
            + ",\"construct_seconds\":" + constructSeconds
            + ",\"consistency_seconds\":" + consistencySeconds
            + ",\"positive_query_seconds\":" + positiveSeconds
            + ",\"negative_query_seconds\":" + negativeSeconds
            + ",\"reasoner_version\":" + quote(version)
            + ",\"java_version\":" + quote(System.getProperty("java.version"))
            + ",\"positive\":" + array(positiveRows)
            + ",\"negative\":" + array(negativeRows) + "}");
    }
}
