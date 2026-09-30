"""GraphQL operation documents recovered from Jino's loaded frontend code."""

DOMAINS_LIST = """
  query DomainsList($sort: [UserDomainSortEnum]) {
    me {
      domain(sort: $sort) {
        edges {
          node {
            id
            domain
            zone
            expireDate
            isSubdomain
            isExpired
            expiring
            autorenewDomain
            hasDnsZone
            forceHttps
            ipv6Enabled
            management
            canBeManaged
            identificationRequired
            dnssecSupport
            mail { spfEnabled dkimEnabled }
            service { name title }
            renewal { renewalAvailable }
            emailVerification {
              required
              suspended
              deadline
              canResendEmail
              email
              subject
              registrar
            }
          }
        }
      }
    }
  }
"""

DNS_RECORDS = """
  query DnsRecords($id: ID!) {
    node(id: $id) {
      ... on UserDomain {
        dns {
          changeable
          records {
            id
            type
            domain
            value
            unchangeable
            subdomainDisplay
            details {
              ... on DNSARecord { ip }
              ... on DNSAAAARecord { ip }
              ... on DNSNSRecord { ns }
            }
          }
        }
      }
    }
  }
"""

DOMAIN_INFO = """
        query DomainInfo($domain: String!) {
          me { legacy { domains { getDomainInfo(domain: $domain) } } }
        }
"""

DOMAIN_NS = """
        query DomainNS($id: ID!) {
          node(id: $id) { ... on UserDomain { registrarInfo { nservers nsChangeable } } }
        }
"""

DOMAIN_RENEWAL_INFO = """
      query DomainInfo($id: ID!) {
        node(id: $id) {
          ... on UserDomain {
            expireDate
            registrarInfo { state }
            renewal {
              renewalAvailable
              renewalCost
              canBeRenewedFromBalance
              autorenewalEnabled
              autorenewalAvailable
              expireDate
              isExpired
              expiring
              premium
            }
          }
        }
      }
"""

CONTACTS = """
    query DomainContacts($domain: String!) {
      me {
        legacy {
          domains {
            getContacts(domain: $domain)
          }
        }
      }
    }
"""

SSL_INFO = """
      query DomainSSL($id: ID!) {
        node(id: $id) {
          ... on UserDomain {
            sslCert {
              notBefore
              notAfter
              caName
              crt {
                issuer { CN O }
                altSubjects { DNS }
              }
            }
            sslCertRequest { state }
          }
        }
      }
"""

ADD_RECORD = {
    "A": """mutation AddA($domain: String!, $subdomain: String, $ip: String!) {
        me { legacy { dns { addA(domain: $domain, subdomain: $subdomain, ip: $ip, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "AAAA": """mutation AddAAAA($domain: String!, $subdomain: String, $ip: String!) {
        me { legacy { dns { addAAAA(domain: $domain, subdomain: $subdomain, ip: $ip, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "CNAME": """mutation AddCNAME($domain: String!, $subdomain: String, $cname: String!) {
        me { legacy { dns { addCNAME(domain: $domain, subdomain: $subdomain, cname: $cname, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "MX": """mutation AddMX($domain: String!, $subdomain: String, $mx: String!, $priority: Int) {
        me { legacy { dns { addMX(domain: $domain, subdomain: $subdomain, mx: $mx, priority: $priority, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "TXT": """mutation AddTXT($domain: String!, $subdomain: String!, $txt: String!) {
        me { legacy { dns { addTXT(domain: $domain, subdomain: $subdomain, txt: $txt, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "NS": """mutation AddNS($domain: String!, $subdomain: String, $ns: String!) {
        me { legacy { dns { addNS(domain: $domain, subdomain: $subdomain, ns: $ns, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "SRV": """mutation AddSRV($domain: String!, $service: String, $priority: Int, $weight: Int, $port: Int, $target: String) {
        me { legacy { dns { addSRV(domain: $domain, service: $service, priority: $priority, weight: $weight, port: $port, target: $target, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "CAA": """mutation AddCAA($domain: String!, $subdomain: String, $flags: Int, $tag: String, $caa: String) {
        me { legacy { dns { addCAA(domain: $domain, subdomain: $subdomain, flags: $flags, tag: $tag, caa: $caa, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "SPF": """mutation AddSPF($domain: String!, $subdomain: String!, $spf: String!) {
        me { legacy { dns { addSPF(domain: $domain, subdomain: $subdomain, spf: $spf, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "SSHFP": """mutation AddSSHFP($domain: String!, $subdomain: String, $algorithm: Int, $hashType: Int, $fingerprint: String) {
        me { legacy { dns { addSSHFP(domain: $domain, subdomain: $subdomain, algorithm: $algorithm, hashType: $hashType, fingerprint: $fingerprint, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "NAPTR": """mutation AddNAPTR($domain: String!, $subdomain: String, $order: Int, $preference: Int, $flags: String, $service: String, $regexp: String, $replacement: String) {
        me { legacy { dns { addNAPTR(domain: $domain, subdomain: $subdomain, order: $order, preference: $preference, flags: $flags, service: $service, regexp: $regexp, replacement: $replacement, validateAll: true, camelCaseErrors: true) } } }
      }""",
}

UPDATE_RECORD = {
    "A": """mutation UpdateA($domain: String!, $recordId: Int!, $subdomain: String, $ip: String!) {
        me { legacy { dns { updateA(domain: $domain, recordId: $recordId, subdomain: $subdomain, ip: $ip, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "AAAA": """mutation UpdateAAAA($domain: String!, $recordId: Int!, $subdomain: String, $ip: String!) {
        me { legacy { dns { updateAAAA(domain: $domain, recordId: $recordId, subdomain: $subdomain, ip: $ip, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "CNAME": """mutation UpdateCNAME($domain: String!, $recordId: Int!, $subdomain: String, $cname: String!) {
        me { legacy { dns { updateCNAME(domain: $domain, recordId: $recordId, subdomain: $subdomain, cname: $cname, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "MX": """mutation UpdateMX($domain: String!, $recordId: Int!, $subdomain: String, $mx: String!, $priority: Int) {
        me { legacy { dns { updateMX(domain: $domain, recordId: $recordId, subdomain: $subdomain, mx: $mx, priority: $priority, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "TXT": """mutation UpdateTXT($domain: String!, $recordId: Int!, $subdomain: String, $txt: String!) {
        me { legacy { dns { updateTXT(domain: $domain, recordId: $recordId, subdomain: $subdomain, txt: $txt, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "NS": """mutation UpdateNS($domain: String!, $recordId: Int!, $subdomain: String, $ns: String!) {
        me { legacy { dns { updateNS(domain: $domain, recordId: $recordId, subdomain: $subdomain, ns: $ns, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "SRV": """mutation UpdateSRV($domain: String!, $recordId: Int!, $service: String, $priority: Int, $weight: Int, $port: Int, $target: String) {
        me { legacy { dns { updateSRV(domain: $domain, recordId: $recordId, service: $service, priority: $priority, weight: $weight, port: $port, target: $target, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "CAA": """mutation UpdateCAA($domain: String!, $recordId: Int!, $subdomain: String, $flags: Int, $tag: String, $caa: String) {
        me { legacy { dns { updateCAA(domain: $domain, recordId: $recordId, subdomain: $subdomain, flags: $flags, tag: $tag, caa: $caa, validateAll: true, camelCaseErrors: true) } } }
      }""",
    "SPF": """mutation UpdateSPF($domain: String!, $recordId: Int!, $subdomain: String, $spf: String!) {
        me { legacy { dns { updateSPF(domain: $domain, recordId: $recordId, subdomain: $subdomain, spf: $spf, validateAll: true, camelCaseErrors: true) } } }
      }""",
}

DELETE_RECORD = """
      mutation DelRecord($domain: String!, $recordId: Int!) {
        me { legacy { dns { delRecord(domain: $domain, recordId: $recordId, validateAll: true, camelCaseErrors: true) } } }
      }
"""

RESET_ZONE = """
      mutation ResetZone($domain: String!) {
        me {
          legacy {
            dns {
              resetZone(domain: $domain)
            }
          }
        }
      }
"""

SET_WWW = """
      mutation SetWWW($domain: String!, $mode: String!) {
        me {
          legacy {
            domains {
              setDomainWWWRedirect(domain: $domain, mode: $mode)
            }
          }
        }
      }
"""

SET_IPV6_TEMPLATE = """
      mutation SetIPv6($domain: String!) {
        me {
          legacy {
            domains {
              {action}(domain: $domain)
            }
          }
        }
      }
"""

UPDATE_NAMESERVERS = """
        mutation UpdateNS($domain: String!, $nservers: [String]) {
          me { legacy { domains { updateDomainNameservers(domain: $domain, nservers: $nservers, validateAll: true, camelCaseErrors: true) } } }
        }
"""

UPDATE_CONTACT = """
      mutation UpdateContact($domain: String!, $contactType: String!, $data: ExJSONString!) {
        me {
          legacy {
            domains {
              updateContact(domain: $domain, contactType: $contactType, data: $data)
            }
          }
        }
      }
"""

REQUEST_SSL = """
      mutation RequestSSL($domain: String!, $wildcard: Boolean) {
        me {
          legacy {
            requestDomainSSLCert(domain: $domain, wildcard: $wildcard)
          }
        }
      }
"""

ADD_SSL_CERT = """
      mutation AddSSLCert($domain: String!, $crt: String!, $key: String!, $subs: [String], $password: String) {
        me {
          legacy {
            addDomainSSLCert(domain: $domain, crt: $crt, key: $key, subs: $subs, password: $password)
          }
        }
      }
"""

DELETE_SSL = """
      mutation DeleteSSL($domain: String!) {
        me {
          legacy {
            deleteDomainSSLCert(domain: $domain)
          }
        }
      }
"""

SET_FORCE_HTTPS_TEMPLATE = """
      mutation SetForceHttps($domain: String!) {
        me { legacy { {action}(domain: $domain, validateAll: true, camelCaseErrors: true) } }
      }
"""

ADD_SUBDOMAIN = """
      mutation AddDomain($domainName: String!) {
        me {
          legacy {
            domains {
              addDomain(domainName: $domainName)
            }
          }
        }
      }
"""

ADD_EXISTING_DOMAIN = """
    mutation AddDomain($domainName: String!, $sendEmail: Boolean) {
      me {
        legacy {
          domains {
            addDomain(domainName: $domainName, sendEmail: $sendEmail, validateAll: true, camelCaseErrors: true)
          }
        }
      }
    }
"""
